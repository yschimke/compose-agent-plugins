import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import {
  chmodSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import http from 'node:http';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

const PROXY = path.resolve(import.meta.dirname, '..', 'src', 'scripts', 'mcp-proxy.mjs');
const SIDECAR = path.resolve(import.meta.dirname, '..', 'src', 'sidecars', 'launch.mjs');

function createFakeBackendScript(dir, spawnLogPath) {
  const scriptPath = path.join(dir, 'fake-mcp.mjs');
  writeFileSync(
    scriptPath,
    `#!/usr/bin/env node
import { appendFileSync } from 'node:fs';
const logPath = ${JSON.stringify(spawnLogPath)};
appendFileSync(logPath, 'spawn:' + process.pid + '\\n');

let buf = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (chunk) => {
  buf += chunk;
  let nl;
  while ((nl = buf.indexOf('\\n')) !== -1) {
    const line = buf.slice(0, nl).replace(/\\r$/, '');
    buf = buf.slice(nl + 1);
    if (!line.trim()) continue;
    const msg = JSON.parse(line);
    if (msg.method === 'initialize') {
      process.stdout.write(JSON.stringify({
        jsonrpc: '2.0',
        id: msg.id,
        result: {
          protocolVersion: '2025-03-26',
          capabilities: { tools: { listChanged: true }, resources: { subscribe: true }, prompts: {} },
          serverInfo: { name: 'fake-mcp', version: '1.0.0' },
        },
      }) + '\\n');
    } else if (msg.method === 'tools/list') {
      process.stdout.write(JSON.stringify({
        jsonrpc: '2.0',
        id: msg.id,
        result: { tools: [{ name: 'render_preview' }, { name: 'android_simulator_launch' }, { name: 'android_simulator_stop' }] },
      }) + '\\n');
    } else if (msg.method === 'resources/list') {
      process.stdout.write(JSON.stringify({
        jsonrpc: '2.0',
        id: msg.id,
        result: { resources: [{ uri: 'ui://compose-preview/viewer', name: 'viewer' }] },
      }) + '\\n');
    } else if (msg.method === 'prompts/list') {
      process.stdout.write(JSON.stringify({
        jsonrpc: '2.0',
        id: msg.id,
        result: { prompts: [{ name: 'review_preview' }] },
      }) + '\\n');
    } else if (msg.method === 'resources/subscribe' || msg.method === 'resources/unsubscribe') {
      process.stdout.write(JSON.stringify({ jsonrpc: '2.0', id: msg.id, result: {} }) + '\\n');
    } else if (msg.method === 'tools/call') {
      if (msg.params?.name === 'need_roots') {
        // Ask host for roots/list before answering.
        const reqId = 'srv-roots-' + msg.id;
        pendingRoots.set(reqId, msg.id);
        process.stdout.write(JSON.stringify({ jsonrpc: '2.0', id: reqId, method: 'roots/list' }) + '\\n');
      } else {
        process.stdout.write(JSON.stringify({
          jsonrpc: '2.0',
          id: msg.id,
          result: { content: [{ type: 'text', text: 'ok:' + msg.params?.name + ':pid=' + process.pid }] },
        }) + '\\n');
      }
    } else if (msg.method === undefined && msg.id && pendingRoots.has(msg.id)) {
      const clientId = pendingRoots.get(msg.id);
      pendingRoots.delete(msg.id);
      process.stdout.write(JSON.stringify({
        jsonrpc: '2.0',
        id: clientId,
        result: { content: [{ type: 'text', text: 'roots=' + JSON.stringify(msg.result?.roots || []) }] },
      }) + '\\n');
    }
  }
});
const pendingRoots = new Map();
process.stdin.on('end', () => {
  appendFileSync(logPath, 'exit:' + process.pid + '\\n');
  process.exit(0);
});
`,
    'utf8',
  );
  chmodSync(scriptPath, 0o755);
  return scriptPath;
}

class JsonRpcClient {
  constructor(proc) {
    this.proc = proc;
    this.nextId = 1;
    this.pending = new Map();
    this.serverRequests = [];
    this.onServerRequest = null;
    let buf = '';
    proc.stdout.setEncoding('utf8');
    proc.stdout.on('data', (chunk) => {
      buf += chunk;
      let nl;
      while ((nl = buf.indexOf('\n')) !== -1) {
        const line = buf.slice(0, nl).replace(/\r$/, '');
        buf = buf.slice(nl + 1);
        if (!line.trim()) continue;
        const msg = JSON.parse(line);
        if (typeof msg.method === 'string' && msg.id !== undefined) {
          this.serverRequests.push(msg);
          if (this.onServerRequest) this.onServerRequest(msg);
        } else if (msg.id !== undefined && this.pending.has(msg.id)) {
          const { resolve } = this.pending.get(msg.id);
          this.pending.delete(msg.id);
          resolve(msg);
        }
      }
    });
  }

  request(method, params) {
    const id = this.nextId++;
    const payload = { jsonrpc: '2.0', id, method };
    if (params !== undefined) payload.params = params;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`Timed out waiting for response to ${method} (id=${id})`));
      }, 5000);
      this.pending.set(id, {
        resolve: (msg) => {
          clearTimeout(timer);
          resolve(msg);
        },
      });
      this.proc.stdin.write(`${JSON.stringify(payload)}\n`);
    });
  }

  notify(method, params) {
    const payload = { jsonrpc: '2.0', method };
    if (params !== undefined) payload.params = params;
    this.proc.stdin.write(`${JSON.stringify(payload)}\n`);
  }

  respond(id, result) {
    this.proc.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', id, result })}\n`);
  }
}

function readLogLines(logPath) {
  if (!existsSync(logPath)) return [];
  return readFileSync(logPath, 'utf8').trim().split('\n').filter(Boolean);
}

async function waitUntil(predicate, timeoutMs = 4000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await predicate()) return;
    await new Promise((r) => setTimeout(r, 40));
  }
  throw new Error('Timed out waiting for condition');
}

test('mcp-proxy caches handshake/discovery, wakes lazily on tools/call, and shuts down on idle', async (t) => {
  const tmpDir = mkdtempSync(path.join(os.tmpdir(), 'mcp-proxy-test-'));
  const spawnLog = path.join(tmpDir, 'spawns.log');
  const cacheFile = path.join(tmpDir, 'proxy-cache.json');
  const fakeBackend = createFakeBackendScript(tmpDir, spawnLog);

  t.after(() => {
    rmSync(tmpDir, { recursive: true, force: true });
  });

  // Session 1 (cold cache): spawns backend once to populate cache, then exits cleanly.
  const proc1 = spawn(process.execPath, [PROXY, process.execPath, fakeBackend], {
    env: {
      ...process.env,
      COMPOSE_PREVIEW_MCP_PROXY_CACHE: cacheFile,
      COMPOSE_PREVIEW_MCP_IDLE_TIMEOUT_MS: '0',
    },
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  const client1 = new JsonRpcClient(proc1);
  const init1 = await client1.request('initialize', { protocolVersion: '2025-03-26', capabilities: {} });
  assert.equal(init1.result.serverInfo.name, 'fake-mcp');
  client1.notify('notifications/initialized');
  const tools1 = await client1.request('tools/list');
  assert.equal(tools1.result.tools.length, 3);
  const res1 = await client1.request('resources/list');
  assert.equal(res1.result.resources.length, 1);
  const prompts1 = await client1.request('prompts/list');
  assert.equal(prompts1.result.prompts.length, 1);
  proc1.stdin.end();
  await new Promise((resolve) => proc1.once('exit', resolve));

  assert.equal(readLogLines(spawnLog).filter((l) => l.startsWith('spawn:')).length, 1);

  // Session 2 (warm cache): initialize + all */list + ping must NOT spawn any backend!
  const proc2 = spawn(process.execPath, [PROXY, process.execPath, fakeBackend], {
    env: {
      ...process.env,
      COMPOSE_PREVIEW_MCP_PROXY_CACHE: cacheFile,
      COMPOSE_PREVIEW_MCP_IDLE_TIMEOUT_MS: '250',
    },
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  t.after(() => proc2.kill('SIGTERM'));
  const client2 = new JsonRpcClient(proc2);

  const init2 = await client2.request('initialize', { protocolVersion: '2025-03-26', capabilities: { roots: {} } });
  assert.equal(init2.result.serverInfo.name, 'fake-mcp');
  client2.notify('notifications/initialized');
  const ping2 = await client2.request('ping');
  assert.deepEqual(ping2.result, {});
  const tools2 = await client2.request('tools/list');
  assert.equal(tools2.result.tools.length, 3);
  const res2 = await client2.request('resources/list');
  assert.equal(res2.result.resources.length, 1);
  const prompts2 = await client2.request('prompts/list');
  assert.equal(prompts2.result.prompts.length, 1);

  // Still only 1 spawn total (from Session 1)!
  assert.equal(readLogLines(spawnLog).filter((l) => l.startsWith('spawn:')).length, 1);

  // First real tools/call wakes backend and forwards server-to-client roots/list!
  client2.onServerRequest = (req) => {
    if (req.method === 'roots/list') {
      client2.respond(req.id, { roots: [{ uri: 'file:///workspace' }] });
    }
  };
  const call1 = await client2.request('tools/call', { name: 'need_roots', arguments: {} });
  assert.match(call1.result.content[0].text, /file:\/\/\/workspace/);
  assert.equal(readLogLines(spawnLog).filter((l) => l.startsWith('spawn:')).length, 2);

  // Wait for idle timeout (250ms) -> backend exits cleanly while proxy stays alive!
  await waitUntil(() => readLogLines(spawnLog).filter((l) => l.startsWith('exit:')).length >= 2);
  assert.equal(proc2.exitCode, null, 'proxy must stay alive after idle backend shutdown');

  // Next tools/call transparently respawns backend!
  const call2 = await client2.request('tools/call', { name: 'render_preview', arguments: {} });
  assert.match(call2.result.content[0].text, /^ok:render_preview:pid=/);
  assert.equal(readLogLines(spawnLog).filter((l) => l.startsWith('spawn:')).length, 3);

  proc2.stdin.end();
  await new Promise((resolve) => proc2.once('exit', resolve));
});

test('mcp-proxy defers idle shutdown while subscriptions or simulators are active', async (t) => {
  const tmpDir = mkdtempSync(path.join(os.tmpdir(), 'mcp-proxy-active-'));
  const spawnLog = path.join(tmpDir, 'spawns.log');
  const cacheFile = path.join(tmpDir, 'proxy-cache.json');
  const fakeBackend = createFakeBackendScript(tmpDir, spawnLog);

  t.after(() => {
    rmSync(tmpDir, { recursive: true, force: true });
  });

  const proc = spawn(process.execPath, [PROXY, process.execPath, fakeBackend], {
    env: {
      ...process.env,
      COMPOSE_PREVIEW_MCP_PROXY_CACHE: cacheFile,
      COMPOSE_PREVIEW_MCP_IDLE_TIMEOUT_MS: '200',
    },
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  t.after(() => proc.kill('SIGTERM'));
  const client = new JsonRpcClient(proc);

  await client.request('initialize', { protocolVersion: '2025-03-26', capabilities: {} });
  client.notify('notifications/initialized');

  // Launch simulator -> idle timer must NOT stop backend while simulator is running.
  await client.request('tools/call', { name: 'android_simulator_launch', arguments: {} });
  await new Promise((r) => setTimeout(r, 400));
  assert.equal(readLogLines(spawnLog).filter((l) => l.startsWith('exit:')).length, 0);

  // Stop simulator -> backend shuts down after idle window.
  await client.request('tools/call', { name: 'android_simulator_stop', arguments: {} });
  await waitUntil(() => readLogLines(spawnLog).filter((l) => l.startsWith('exit:')).length === 1);

  proc.stdin.end();
  await new Promise((resolve) => proc.once('exit', resolve));
});

test('mcp-proxy launches cached compose-preview-mcp directly without parent CLI JVM', async (t) => {
  const tmpDir = mkdtempSync(path.join(os.tmpdir(), 'mcp-proxy-direct-'));
  const spawnLog = path.join(tmpDir, 'spawns.log');
  const cacheRoot = path.join(tmpDir, 'composeai', 'preview-mcp');
  const binDir = path.join(cacheRoot, '4.26.0', 'bin');
  mkdirSync(binDir, { recursive: true });
  writeFileSync(path.join(cacheRoot, '.latest-check'), '');

  const directBinary = path.join(binDir, 'compose-preview-mcp');
  const fakeBackend = createFakeBackendScript(tmpDir, spawnLog);
  writeFileSync(directBinary, `#!/bin/sh\nexec "${process.execPath}" "${fakeBackend}" "$@"\n`, 'utf8');
  chmodSync(directBinary, 0o755);

  t.after(() => {
    rmSync(tmpDir, { recursive: true, force: true });
  });

  // Pass `compose-preview mcp serve` even though `compose-preview` is NOT on PATH —
  // proving the proxy bypassed the parent CLI launcher and ran the cached binary directly!
  const proc = spawn(process.execPath, [PROXY, 'compose-preview', 'mcp', 'serve'], {
    env: {
      ...process.env,
      XDG_CACHE_HOME: tmpDir,
      COMPOSE_PREVIEW_MCP_IDLE_TIMEOUT_MS: '0',
    },
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  t.after(() => proc.kill('SIGTERM'));
  const client = new JsonRpcClient(proc);

  const init = await client.request('initialize', { protocolVersion: '2025-03-26', capabilities: {} });
  assert.equal(init.result.serverInfo.name, 'fake-mcp');
  assert.equal(readLogLines(spawnLog).filter((l) => l.startsWith('spawn:')).length, 1);

  proc.stdin.end();
  await new Promise((resolve) => proc.once('exit', resolve));
});

test('mcp-proxy bypasses cached initialize when client requests a different protocolVersion', async (t) => {
  const tmpDir = mkdtempSync(path.join(os.tmpdir(), 'mcp-proxy-proto-'));
  const spawnLog = path.join(tmpDir, 'spawns.log');
  const cacheFile = path.join(tmpDir, 'proxy-cache.json');
  const fakeBackend = createFakeBackendScript(tmpDir, spawnLog);

  t.after(() => {
    rmSync(tmpDir, { recursive: true, force: true });
  });

  // Populate cache with 2025-03-26.
  const proc1 = spawn(process.execPath, [PROXY, process.execPath, fakeBackend], {
    env: {
      ...process.env,
      COMPOSE_PREVIEW_MCP_PROXY_CACHE: cacheFile,
      COMPOSE_PREVIEW_MCP_IDLE_TIMEOUT_MS: '0',
    },
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  const client1 = new JsonRpcClient(proc1);
  await client1.request('initialize', { protocolVersion: '2025-03-26', capabilities: {} });
  proc1.stdin.end();
  await new Promise((resolve) => proc1.once('exit', resolve));
  assert.equal(readLogLines(spawnLog).filter((l) => l.startsWith('spawn:')).length, 1);

  // Second session requesting 2024-11-05 must NOT replay cached 2025-03-26 without waking backend.
  const proc2 = spawn(process.execPath, [PROXY, process.execPath, fakeBackend], {
    env: {
      ...process.env,
      COMPOSE_PREVIEW_MCP_PROXY_CACHE: cacheFile,
      COMPOSE_PREVIEW_MCP_IDLE_TIMEOUT_MS: '0',
    },
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  t.after(() => proc2.kill('SIGTERM'));
  const client2 = new JsonRpcClient(proc2);
  await client2.request('initialize', { protocolVersion: '2024-11-05', capabilities: {} });
  assert.equal(readLogLines(spawnLog).filter((l) => l.startsWith('spawn:')).length, 2);

  proc2.stdin.end();
  await new Promise((resolve) => proc2.once('exit', resolve));
});

function allocatePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.on('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const addr = srv.address();
      srv.close(() => resolve(addr.port));
    });
  });
}

test('sidecar stops idle child backend and restarts lazily on next visit', async (t) => {
  const tmpDir = mkdtempSync(path.join(os.tmpdir(), 'sidecar-idle-test-'));
  const projectDir = path.join(tmpDir, 'proj');
  mkdirSync(projectDir, { recursive: true });
  writeFileSync(path.join(projectDir, 'settings.gradle.kts'), 'rootProject.name = "demo"\n');

  const spawnLog = path.join(tmpDir, 'sidecar-spawns.log');
  const fakeCli = path.join(tmpDir, 'compose-preview');
  writeFileSync(
    fakeCli,
    `#!${process.execPath}
import { appendFileSync } from 'node:fs';
import http from 'node:http';
const args = process.argv.slice(2);
const portIdx = args.indexOf('--port');
const port = Number(args[portIdx + 1]);
appendFileSync(${JSON.stringify(spawnLog)}, 'start:' + process.pid + '\\n');
const srv = http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/plain' });
  res.end('hello-from-fake-browse');
});
srv.listen(port, '127.0.0.1');
process.on('SIGTERM', () => {
  appendFileSync(${JSON.stringify(spawnLog)}, 'stop:' + process.pid + '\\n');
  srv.close(() => process.exit(0));
});
`,
    'utf8',
  );
  chmodSync(fakeCli, 0o755);

  const sidecarPort = await allocatePort();
  const proc = spawn(process.execPath, [SIDECAR, 'browse'], {
    env: {
      ...process.env,
      ANTIGRAVITY_SIDECAR_WEB_PORT: String(sidecarPort),
      COMPOSE_PREVIEW_CLI: fakeCli,
      COMPOSE_PREVIEW_WORKSPACE: projectDir,
      COMPOSE_PREVIEW_SIDECAR_IDLE_TIMEOUT_MS: '300',
      XDG_CACHE_HOME: tmpDir,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  t.after(async () => {
    // The sidecar and its fake CLI write into tmpDir while they shut down (the
    // spawn log's stop line, the XDG cache), so wait for the sidecar to exit,
    // and retry the delete for any write its child makes after that.
    if (proc.exitCode === null && proc.signalCode === null) {
      const exited = new Promise((resolve) => proc.once('exit', resolve));
      proc.kill('SIGTERM');
      await exited;
    }
    rmSync(tmpDir, { recursive: true, force: true, maxRetries: 10, retryDelay: 50 });
  });

  const baseUrl = `http://127.0.0.1:${sidecarPort}`;
  await waitUntil(async () => {
    try {
      const r = await fetch(`${baseUrl}/__sidecar/status`);
      return r.ok;
    } catch {
      return false;
    }
  });

  // Trigger lazy start
  await fetch(`${baseUrl}/`);
  await waitUntil(async () => {
    const s = await (await fetch(`${baseUrl}/__sidecar/status`)).json();
    return s.state === 'ready';
  });
  const body1 = await (await fetch(`${baseUrl}/`)).text();
  assert.equal(body1, 'hello-from-fake-browse');

  // Wait for idle shutdown -> returns to idle state and stops child
  await waitUntil(async () => {
    const s = await (await fetch(`${baseUrl}/__sidecar/status`)).json();
    return s.state === 'idle';
  });
  await waitUntil(() => readLogLines(spawnLog).filter((l) => l.startsWith('stop:')).length === 1);

  // Next visit restarts backend lazily
  await fetch(`${baseUrl}/`);
  await waitUntil(async () => {
    const s = await (await fetch(`${baseUrl}/__sidecar/status`)).json();
    return s.state === 'ready';
  });
  assert.equal(readLogLines(spawnLog).filter((l) => l.startsWith('start:')).length, 2);
});
