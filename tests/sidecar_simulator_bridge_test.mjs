import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import http from 'node:http';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

const LAUNCHER = path.resolve(import.meta.dirname, '..', 'src', 'sidecars', 'launch.mjs');

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

async function waitForHttp(url, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url);
      if (res.ok) return res;
    } catch {
      // retry
    }
    await new Promise((r) => setTimeout(r, 80));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

test('sidecar proxies simulator bridge with server-side auth token and embeds simulator UI', async (t) => {
  const tmpDir = mkdtempSync(path.join(os.tmpdir(), 'sidecar-sim-test-'));
  const token = 'secret-bridge-token';
  const receivedTokens = [];

  const fakeBridge = http.createServer((req, res) => {
    if (req.url === '/') {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end('<!doctype html><title>Fake Simulator UI</title>');
      return;
    }
    receivedTokens.push(req.headers['x-simulator-token']);
    if (req.headers['x-simulator-token'] !== token) {
      res.writeHead(401, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'unauthorized' }));
      return;
    }
    if (req.url === '/api/simulators') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(
        JSON.stringify({
          simulators: [{ id: 'sim-1', apk: 'phone-debug.apk', devices: ['phone', 'watch'], running: true }],
        }),
      );
      return;
    }
    res.writeHead(404);
    res.end();
  });

  await new Promise((resolve) => fakeBridge.listen(0, '127.0.0.1', resolve));
  const bridgePort = fakeBridge.address().port;

  const cacheDir = path.join(tmpDir, 'composeai');
  mkdirSync(cacheDir, { recursive: true });
  writeFileSync(
    path.join(cacheDir, 'simulator-bridge.json'),
    JSON.stringify({
      pid: process.pid,
      port: bridgePort,
      token,
      simulators: [{ id: 'sim-1', apk: 'phone-debug.apk', devices: ['phone', 'watch'], running: true }],
    }),
  );

  const sidecarPort = await allocatePort();
  const proc = spawn(process.execPath, [LAUNCHER, 'browse'], {
    env: {
      ...process.env,
      ANTIGRAVITY_SIDECAR_WEB_PORT: String(sidecarPort),
      XDG_CACHE_HOME: tmpDir,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  t.after(() => {
    proc.kill('SIGTERM');
    fakeBridge.close();
    rmSync(tmpDir, { recursive: true, force: true });
  });

  const baseUrl = `http://127.0.0.1:${sidecarPort}`;
  await waitForHttp(`${baseUrl}/__sidecar/status`);

  // Dedicated /simulator Auxiliary Pane route serves the live simulator without starting browse.
  const simPaneRes = await fetch(`${baseUrl}/simulator`);
  assert.equal(simPaneRes.status, 200);
  const simPaneHtml = await simPaneRes.text();
  assert.match(simPaneHtml, /iframe class="sim-frame" src="\/__sidecar\/simulator-ui\?transport=http&amp;apiBase=\/__sidecar\/sim"/);

  const beforeStatus = await (await fetch(`${baseUrl}/__sidecar/status`)).json();
  assert.equal(beforeStatus.mode, 'browse');
  assert.equal(beforeStatus.state, 'idle');
  assert.equal(beforeStatus.bridgeActive, true);
  assert.deepEqual(beforeStatus.bridgeSimulators[0].devices, ['phone', 'watch']);

  const pageRes = await fetch(`${baseUrl}/?mode=simulator`);
  assert.equal(pageRes.status, 200);
  const html = await pageRes.text();
  assert.match(html, /iframe class="sim-frame" src="\/__sidecar\/simulator-ui\?transport=http&amp;apiBase=\/__sidecar\/sim"/);

  const statusRes = await fetch(`${baseUrl}/__sidecar/status`);
  const status = await statusRes.json();
  assert.equal(status.mode, 'simulator');
  assert.equal(status.bridgeActive, true);
  assert.deepEqual(status.bridgeSimulators[0].devices, ['phone', 'watch']);

  const simRes = await fetch(`${baseUrl}/__sidecar/sim`);
  assert.equal(simRes.status, 200);
  const simData = await simRes.json();
  assert.equal(simData.simulators[0].id, 'sim-1');
  assert.deepEqual(receivedTokens, [token]);

  const uiRes = await fetch(`${baseUrl}/__sidecar/simulator-ui`);
  assert.equal(uiRes.status, 200);
  assert.match(await uiRes.text(), /Fake Simulator UI/);
});
