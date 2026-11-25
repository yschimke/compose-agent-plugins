#!/usr/bin/env node
// Lazy-start, idle-shutdown stdio MCP proxy for `compose-preview-mcp`.
//
// Keeps the MCP stdio pipe attached to the host (Claude Desktop/Code, Codex, Cursor, Antigravity,
// Gemini CLI) with zero JVM cost while idle:
//   - Answers `initialize`, `ping`, and cached `*/list` discovery requests immediately without
//     spawning a JVM when a valid cache exists for the installed `compose-preview-mcp` binary.
//   - Spawns `compose-preview-mcp` directly on first real use (`tools/call`, `resources/read`,
//     `prompts/get`, uncached list, etc.), bypassing the parent `compose-preview` launcher JVM
//     when the cached distribution is up to date.
//   - Cleanly shuts down the backend JVM after an idle period (default 5 minutes, configurable via
//     `COMPOSE_PREVIEW_MCP_IDLE_TIMEOUT_MS`; 0 disables) while keeping the host stdio pipe open so
//     hosts never report the server as crashed or stopped.

import { spawn } from 'node:child_process';
import {
  accessSync,
  constants,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  renameSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const DEFAULT_IDLE_TIMEOUT_MS = 5 * 60 * 1000;
const REFRESH_INTERVAL_MS = 24 * 60 * 60 * 1000;
const SHUTDOWN_TERM_GRACE_MS = 5000;
const SHUTDOWN_KILL_GRACE_MS = 2000;
const CACHE_SCHEMA_VERSION = 1;

const fallbackArgv = process.argv.slice(2);
if (fallbackArgv.length === 0) {
  process.stderr.write('usage: mcp-proxy.mjs <command> [args...]\n');
  process.exit(2);
}

function parseIdleTimeoutMs() {
  const raw = process.env.COMPOSE_PREVIEW_MCP_IDLE_TIMEOUT_MS;
  if (raw == null || raw.trim() === '') return DEFAULT_IDLE_TIMEOUT_MS;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed) || parsed < 0) return DEFAULT_IDLE_TIMEOUT_MS;
  return Math.floor(parsed);
}

const idleTimeoutMs = parseIdleTimeoutMs();

function cacheBaseDir() {
  return process.env.XDG_CACHE_HOME || path.join(os.homedir(), '.cache');
}

function proxyCacheFile() {
  if (process.env.COMPOSE_PREVIEW_MCP_PROXY_CACHE) {
    return process.env.COMPOSE_PREVIEW_MCP_PROXY_CACHE;
  }
  return path.join(cacheBaseDir(), 'composeai', 'mcp', 'proxy-cache.json');
}

function simulatorBridgeFile() {
  return path.join(cacheBaseDir(), 'composeai', 'simulator-bridge.json');
}

function isExecutable(filePath) {
  try {
    accessSync(filePath, constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

function findOnPath(name) {
  const dirs = (process.env.PATH || '').split(path.delimiter).filter(Boolean);
  for (const dir of dirs) {
    const candidate = path.join(dir, name);
    if (isExecutable(candidate)) return candidate;
  }
  return null;
}

function findCliLauncher() {
  if (process.env.COMPOSE_PREVIEW_CLI && isExecutable(process.env.COMPOSE_PREVIEW_CLI)) {
    return process.env.COMPOSE_PREVIEW_CLI;
  }
  const onPath = findOnPath('compose-preview');
  if (onPath) return onPath;
  const fallbacks = [
    path.join(os.homedir(), '.local', 'bin', 'compose-preview'),
    '/opt/homebrew/bin/compose-preview',
    '/usr/local/bin/compose-preview',
  ];
  for (const candidate of fallbacks) {
    if (isExecutable(candidate)) return candidate;
  }
  return null;
}

function parseSemver(version) {
  const match = String(version).match(/^(\d+)\.(\d+)\.(\d+)(?:-(.+))?$/);
  if (!match) return null;
  return {
    major: Number(match[1]),
    minor: Number(match[2]),
    patch: Number(match[3]),
    pre: match[4] || '',
  };
}

function compareSemver(a, b) {
  const pa = parseSemver(a);
  const pb = parseSemver(b);
  if (!pa && !pb) return String(a).localeCompare(String(b));
  if (!pa) return -1;
  if (!pb) return 1;
  if (pa.major !== pb.major) return pa.major - pb.major;
  if (pa.minor !== pb.minor) return pa.minor - pb.minor;
  if (pa.patch !== pb.patch) return pa.patch - pb.patch;
  if (pa.pre === pb.pre) return 0;
  if (!pa.pre) return 1;
  if (!pb.pre) return -1;
  return pa.pre.localeCompare(pb.pre);
}

function stripMcpBinaryFlag(args) {
  const out = [];
  let flagBinary = null;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--mcp-binary' && i + 1 < args.length) {
      flagBinary = args[i + 1].trim();
      i++;
      continue;
    }
    out.push(args[i]);
  }
  return { flagBinary, forwardedArgs: out };
}

function isComposePreviewMcpServe(argv) {
  const base = path.basename(argv[0] || '');
  return (
    (base === 'compose-preview' || base === 'compose-preview.bat') &&
    argv[1] === 'mcp' &&
    argv[2] === 'serve'
  );
}

function resolveDirectMcpCommand(argv) {
  if (process.env.COMPOSE_PREVIEW_MCP_DIRECT === '0') return null;
  if (!isComposePreviewMcpServe(argv)) return null;

  const extraArgs = argv.slice(3);
  const { flagBinary, forwardedArgs } = stripMcpBinaryFlag(extraArgs);

  let binary = null;
  if (flagBinary && isExecutable(flagBinary)) {
    binary = flagBinary;
  } else if (process.env.COMPOSE_PREVIEW_MCP && isExecutable(process.env.COMPOSE_PREVIEW_MCP.trim())) {
    binary = process.env.COMPOSE_PREVIEW_MCP.trim();
  } else {
    const onPath = findOnPath('compose-preview-mcp');
    if (onPath) {
      binary = onPath;
    } else {
      const cacheRoot = path.join(cacheBaseDir(), 'composeai', 'preview-mcp');
      const requestedVersion = (process.env.COMPOSE_PREVIEW_MCP_VERSION || '').trim();
      if (requestedVersion) {
        const candidate = path.join(cacheRoot, requestedVersion, 'bin', 'compose-preview-mcp');
        if (isExecutable(candidate)) binary = candidate;
      } else if (existsSync(cacheRoot)) {
        const offline = process.env.COMPOSE_PREVIEW_OFFLINE === '1';
        const stampFile = path.join(cacheRoot, '.latest-check');
        let refreshFresh = offline;
        if (!refreshFresh && existsSync(stampFile)) {
          try {
            const age = Date.now() - statSync(stampFile).mtimeMs;
            refreshFresh = age >= 0 && age < REFRESH_INTERVAL_MS;
          } catch {
            refreshFresh = false;
          }
        }
        if (refreshFresh) {
          try {
            const versions = readdirSync(cacheRoot)
              .filter((entry) => !entry.startsWith('.'))
              .filter((entry) => isExecutable(path.join(cacheRoot, entry, 'bin', 'compose-preview-mcp')))
              .sort(compareSemver);
            if (versions.length > 0) {
              binary = path.join(cacheRoot, versions[versions.length - 1], 'bin', 'compose-preview-mcp');
            }
          } catch {
            // Fall back to compose-preview mcp serve.
          }
        }
      }
    }
  }

  if (!binary) return null;
  const env = { ...process.env };
  if (!env.COMPOSE_PREVIEW_CLI) {
    const cli = findCliLauncher();
    if (cli) env.COMPOSE_PREVIEW_CLI = cli;
  }
  return { command: binary, args: forwardedArgs, env, direct: true };
}

function resolveLaunchSpec() {
  const direct = resolveDirectMcpCommand(fallbackArgv);
  if (direct) return direct;
  return { command: fallbackArgv[0], args: fallbackArgv.slice(1), env: { ...process.env }, direct: false };
}

function computeCacheKey(spec) {
  let targetPath = spec.command;
  if (!path.isAbsolute(targetPath)) {
    const resolved = findOnPath(targetPath);
    if (resolved) targetPath = resolved;
  }
  let mtimeMs = 0;
  try {
    mtimeMs = Math.floor(statSync(targetPath).mtimeMs);
  } catch {
    mtimeMs = 0;
  }
  return `${targetPath}:${mtimeMs}:${spec.args.join('\0')}`;
}

function loadCache(expectedKey) {
  const file = proxyCacheFile();
  if (!existsSync(file)) return null;
  try {
    const parsed = JSON.parse(readFileSync(file, 'utf8'));
    if (parsed?.schema !== CACHE_SCHEMA_VERSION || parsed?.key !== expectedKey) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function saveCache(cacheObj) {
  const file = proxyCacheFile();
  try {
    mkdirSync(path.dirname(file), { recursive: true });
    const tmp = `${file}.${process.pid}.tmp`;
    writeFileSync(tmp, `${JSON.stringify(cacheObj, null, 2)}\n`, 'utf8');
    renameSync(tmp, file);
  } catch {
    // Non-fatal: cache miss only means next session warms once.
  }
}

function hasActiveSimulatorBridgeForPid(pid) {
  if (!pid) return false;
  try {
    const file = simulatorBridgeFile();
    if (!existsSync(file)) return false;
    const parsed = JSON.parse(readFileSync(file, 'utf8'));
    return (
      Number(parsed?.pid) === pid &&
      Array.isArray(parsed?.simulators) &&
      parsed.simulators.length > 0
    );
  } catch {
    return false;
  }
}

// -- Proxy state ----------------------------------------------------------------------------------

let activeSpec = resolveLaunchSpec();
let cacheKey = computeCacheKey(activeSpec);
let cacheState = loadCache(cacheKey) || {
  schema: CACHE_SCHEMA_VERSION,
  key: cacheKey,
  initialize: null,
  toolsList: null,
  promptsList: null,
  resourcesList: null,
  resourceTemplatesList: null,
};

let clientInitParams = null;
let clientInitialized = false;
let hostClosed = false;

let backend = null;
let backendReady = false;
let backendStopping = false;
let wakePromise = null;
let internalIdCounter = 0;
let pendingInternalInit = null; // { id, resolve, reject }

/** Client requests currently awaiting a response from the backend: idKey -> { id, method, toolName } */
const inFlightClientRequests = new Map();
/** Server-to-client requests currently awaiting a response from the host: idKey -> true */
const inFlightServerRequests = new Set();
/** Active resource subscriptions: uri -> true */
const activeSubscriptions = new Set();
/** Active simulator sessions started in this proxy session (best-effort counter). */
let activeSimulators = 0;
let idleTimer = null;

function idKey(id) {
  return `${typeof id}:${String(id)}`;
}

function writeToHost(msg) {
  if (hostClosed) return;
  try {
    process.stdout.write(`${JSON.stringify(msg)}\n`);
  } catch {
    // Ignore EPIPE when host exits.
  }
}

function writeToBackend(msg) {
  if (!backend || !backend.stdin || backend.stdin.destroyed) return false;
  try {
    backend.stdin.write(`${JSON.stringify(msg)}\n`);
    return true;
  } catch {
    return false;
  }
}

function persistCache() {
  cacheState.schema = CACHE_SCHEMA_VERSION;
  cacheState.key = cacheKey;
  saveCache(cacheState);
}

function clearIdleTimer() {
  if (idleTimer) {
    clearTimeout(idleTimer);
    idleTimer = null;
  }
}

function canIdleShutdown() {
  if (idleTimeoutMs <= 0) return false;
  if (!backend || !backendReady || backendStopping || wakePromise) return false;
  if (inFlightClientRequests.size > 0 || inFlightServerRequests.size > 0) return false;
  if (activeSubscriptions.size > 0 || activeSimulators > 0) return false;
  if (hasActiveSimulatorBridgeForPid(backend.pid)) return false;
  return true;
}

function scheduleIdleShutdown() {
  clearIdleTimer();
  if (!canIdleShutdown()) return;
  idleTimer = setTimeout(() => {
    idleTimer = null;
    if (!canIdleShutdown()) {
      scheduleIdleShutdown();
      return;
    }
    stopBackend('idle');
  }, idleTimeoutMs);
  if (idleTimer.unref) idleTimer.unref();
}

let stoppingBackend = null;

function stopBackend(reason, { waitForExit = false } = {}) {
  clearIdleTimer();
  const proc = backend;
  if (!proc) return Promise.resolve();
  backend = null;
  backendReady = false;
  backendStopping = true;
  stoppingBackend = proc;
  if (reason === 'idle') {
    const secs = Math.round(idleTimeoutMs / 1000);
    process.stderr.write(
      `compose-preview-mcp-proxy: stopping idle backend after ${secs}s (will restart on next tool call)\n`,
    );
  }
  return new Promise((resolve) => {
    let settled = false;
    let termTimer = null;
    let killTimer = null;
    const finish = () => {
      if (settled) return;
      settled = true;
      if (termTimer) clearTimeout(termTimer);
      if (killTimer) clearTimeout(killTimer);
      if (stoppingBackend === proc) stoppingBackend = null;
      if (backend === null) backendStopping = false;
      resolve();
    };

    if (proc.exitCode !== null || proc.signalCode !== null) {
      finish();
      return;
    }

    proc.once('exit', finish);
    try {
      if (proc.stdin && !proc.stdin.destroyed) {
        proc.stdin.end();
      }
    } catch {
      // ignore
    }
    termTimer = setTimeout(() => {
      try {
        proc.kill('SIGTERM');
      } catch {
        // ignore
      }
      killTimer = setTimeout(() => {
        try {
          proc.kill('SIGKILL');
        } catch {
          // ignore
        }
        finish();
      }, SHUTDOWN_KILL_GRACE_MS);
      if (!waitForExit && killTimer.unref) killTimer.unref();
    }, SHUTDOWN_TERM_GRACE_MS);
    if (!waitForExit && termTimer.unref) termTimer.unref();
  });
}

function failInFlightClientRequests(message) {
  for (const [, pending] of inFlightClientRequests) {
    writeToHost({
      jsonrpc: '2.0',
      id: pending.id,
      error: { code: -32603, message },
    });
  }
  inFlightClientRequests.clear();
  inFlightServerRequests.clear();
}

function spawnAndInitBackend(spec) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const finishResolve = () => {
      if (settled) return;
      settled = true;
      resolve();
    };
    const finishReject = (err) => {
      if (settled) return;
      settled = true;
      reject(err);
    };

    const proc = spawn(spec.command, spec.args, {
      env: spec.env,
      stdio: ['pipe', 'pipe', 'inherit'],
    });
    backend = proc;
    backendReady = false;
    backendStopping = false;

    let stdoutBuffer = '';
    proc.stdout.setEncoding('utf8');
    proc.stdout.on('data', (chunk) => {
      stdoutBuffer += chunk;
      let nl;
      while ((nl = stdoutBuffer.indexOf('\n')) !== -1) {
        const line = stdoutBuffer.slice(0, nl).replace(/\r$/, '');
        stdoutBuffer = stdoutBuffer.slice(nl + 1);
        if (!line.trim()) continue;
        let msg;
        try {
          msg = JSON.parse(line);
        } catch {
          continue;
        }
        handleBackendMessage(proc, msg);
      }
    });

    proc.on('error', (err) => {
      if (backend === proc) {
        backend = null;
        backendReady = false;
      }
      if (pendingInternalInit && !settled) {
        pendingInternalInit = null;
        finishReject(err);
      } else {
        failInFlightClientRequests(`compose-preview-mcp backend error: ${err.message}`);
      }
    });

    proc.on('exit', (code, signal) => {
      const wasExpected = backendStopping || hostClosed || backend !== proc;
      if (backend === proc) {
        backend = null;
        backendReady = false;
      }
      activeSimulators = 0;
      if (pendingInternalInit && !settled) {
        pendingInternalInit = null;
        finishReject(
          new Error(
            `compose-preview-mcp exited during startup (code=${code}, signal=${signal || 'none'})`,
          ),
        );
        return;
      }
      if (!wasExpected) {
        failInFlightClientRequests(
          `compose-preview-mcp exited unexpectedly (code=${code}, signal=${signal || 'none'})`,
        );
      }
    });

    const initId = `__proxy_init_${++internalIdCounter}`;
    pendingInternalInit = {
      id: initId,
      resolve: (result) => {
        cacheState.initialize = result;
        persistCache();
        if (clientInitialized) {
          writeToBackend({ jsonrpc: '2.0', method: 'notifications/initialized' });
        }
        backendReady = true;
        finishResolve();
      },
      reject: finishReject,
    };

    const initParams = clientInitParams || {
      protocolVersion: '2025-03-26',
      capabilities: {},
      clientInfo: { name: 'compose-preview-mcp-proxy', version: '1.0.0' },
    };
    writeToBackend({
      jsonrpc: '2.0',
      id: initId,
      method: 'initialize',
      params: initParams,
    });
  });
}

async function ensureBackendRunning() {
  if (backend && backendReady) return;
  if (wakePromise) return wakePromise;

  wakePromise = (async () => {
    activeSpec = resolveLaunchSpec();
    const newKey = computeCacheKey(activeSpec);
    if (newKey !== cacheKey) {
      cacheKey = newKey;
      cacheState = loadCache(cacheKey) || {
        schema: CACHE_SCHEMA_VERSION,
        key: cacheKey,
        initialize: null,
        toolsList: null,
        promptsList: null,
        resourcesList: null,
        resourceTemplatesList: null,
      };
    }

    try {
      await spawnAndInitBackend(activeSpec);
    } catch (err) {
      if (activeSpec.direct) {
        process.stderr.write(
          `compose-preview-mcp-proxy: direct launch failed (${err.message}); falling back to ${fallbackArgv.join(' ')}\n`,
        );
        activeSpec = {
          command: fallbackArgv[0],
          args: fallbackArgv.slice(1),
          env: { ...process.env },
          direct: false,
        };
        cacheKey = computeCacheKey(activeSpec);
        await spawnAndInitBackend(activeSpec);
      } else {
        throw err;
      }
    }
  })();

  try {
    await wakePromise;
  } finally {
    wakePromise = null;
    scheduleIdleShutdown();
  }
}

function handleBackendMessage(proc, msg) {
  if (backend !== proc) return;

  // Response to our synthetic internal initialize request.
  if (
    pendingInternalInit &&
    msg.id === pendingInternalInit.id &&
    (Object.prototype.hasOwnProperty.call(msg, 'result') ||
      Object.prototype.hasOwnProperty.call(msg, 'error'))
  ) {
    const pending = pendingInternalInit;
    pendingInternalInit = null;
    if (msg.error) {
      pending.reject(new Error(msg.error.message || 'initialize failed'));
    } else {
      pending.resolve(msg.result);
    }
    return;
  }

  // Server-to-client request (has both `method` and `id`, e.g., `roots/list`, `elicitation/create`).
  if (typeof msg.method === 'string' && msg.id !== undefined) {
    inFlightServerRequests.add(idKey(msg.id));
    clearIdleTimer();
    writeToHost(msg);
    return;
  }

  // Server-to-client notification (has `method`, no `id`).
  if (typeof msg.method === 'string' && msg.id === undefined) {
    if (msg.method === 'notifications/tools/list_changed') {
      cacheState.toolsList = null;
      persistCache();
    }
    writeToHost(msg);
    return;
  }

  // Response to a forwarded client request.
  if (msg.id !== undefined) {
    const key = idKey(msg.id);
    const pending = inFlightClientRequests.get(key);
    if (pending) {
      inFlightClientRequests.delete(key);
      if (!msg.error && msg.result !== undefined) {
        updateCacheFromResponse(pending, msg.result);
        updateActivityFromToolResponse(pending, msg.result);
      }
    }
    writeToHost(msg);
    scheduleIdleShutdown();
  }
}

function updateCacheFromResponse(pending, result) {
  if (pending.hasCursor) return;
  let dirty = false;
  if (pending.method === 'tools/list') {
    cacheState.toolsList = result;
    dirty = true;
  } else if (pending.method === 'prompts/list') {
    cacheState.promptsList = result;
    dirty = true;
  } else if (pending.method === 'resources/list') {
    cacheState.resourcesList = result;
    dirty = true;
  } else if (pending.method === 'resources/templates/list') {
    cacheState.resourceTemplatesList = result;
    dirty = true;
  }
  if (dirty) persistCache();
}

function updateActivityFromToolResponse(pending, result) {
  if (pending.method === 'resources/subscribe' && pending.uri) {
    activeSubscriptions.add(pending.uri);
  } else if (pending.method === 'resources/unsubscribe' && pending.uri) {
    activeSubscriptions.delete(pending.uri);
  } else if (pending.method === 'tools/call' && !result?.isError) {
    if (pending.toolName === 'android_simulator_launch' || pending.toolName === 'simulator_launch') {
      activeSimulators++;
    } else if (
      pending.toolName === 'android_simulator_stop' ||
      pending.toolName === 'simulator_stop'
    ) {
      activeSimulators = Math.max(0, activeSimulators - 1);
    }
  }
}

function cachedResultFor(method, params) {
  if (params && params.cursor) return null;
  if (method === 'initialize') return cacheState.initialize;
  if (method === 'tools/list') return cacheState.toolsList;
  if (method === 'prompts/list') return cacheState.promptsList;
  if (method === 'resources/list') return cacheState.resourcesList;
  if (method === 'resources/templates/list') return cacheState.resourceTemplatesList;
  return null;
}

async function handleClientMessage(msg) {
  // Response from host to a server-to-client request (e.g., roots/list).
  if (msg.method === undefined && msg.id !== undefined) {
    const key = idKey(msg.id);
    if (inFlightServerRequests.delete(key)) {
      writeToBackend(msg);
      scheduleIdleShutdown();
    }
    return;
  }

  const method = msg.method;
  const isNotification = msg.id === undefined;

  if (method === 'initialize') {
    clientInitParams = msg.params || {};
    const requestedProtocol =
      typeof clientInitParams.protocolVersion === 'string'
        ? clientInitParams.protocolVersion
        : null;
    const cachedProtocol =
      typeof cacheState.initialize?.protocolVersion === 'string'
        ? cacheState.initialize.protocolVersion
        : null;
    const protocolCompatible =
      !requestedProtocol || (cachedProtocol !== null && cachedProtocol === requestedProtocol);
    if (!backend && cacheState.initialize && protocolCompatible) {
      writeToHost({ jsonrpc: '2.0', id: msg.id, result: cacheState.initialize });
      return;
    }
    try {
      await ensureBackendRunning();
      writeToHost({ jsonrpc: '2.0', id: msg.id, result: cacheState.initialize });
    } catch (err) {
      writeToHost({
        jsonrpc: '2.0',
        id: msg.id,
        error: { code: -32603, message: err.message || 'failed to start compose-preview-mcp' },
      });
    }
    return;
  }

  if (method === 'notifications/initialized') {
    clientInitialized = true;
    if (backend && backendReady) {
      writeToBackend(msg);
    }
    return;
  }

  if (method === 'ping' && !isNotification) {
    writeToHost({ jsonrpc: '2.0', id: msg.id, result: {} });
    return;
  }

  // Notifications when backend is asleep do not wake the JVM.
  if (isNotification) {
    if (backend && backendReady) {
      writeToBackend(msg);
      scheduleIdleShutdown();
    }
    return;
  }

  // Serve cached read-only discovery lists without waking the JVM.
  if (!backend) {
    const cached = cachedResultFor(method, msg.params);
    if (cached !== null) {
      writeToHost({ jsonrpc: '2.0', id: msg.id, result: cached });
      return;
    }
  }

  // Wake backend and forward request.
  clearIdleTimer();
  try {
    await ensureBackendRunning();
  } catch (err) {
    writeToHost({
      jsonrpc: '2.0',
      id: msg.id,
      error: { code: -32603, message: err.message || 'failed to start compose-preview-mcp' },
    });
    return;
  }

  const pending = {
    id: msg.id,
    method,
    hasCursor: Boolean(msg.params && msg.params.cursor),
    uri: typeof msg.params?.uri === 'string' ? msg.params.uri : null,
    toolName: typeof msg.params?.name === 'string' ? msg.params.name : null,
  };
  inFlightClientRequests.set(idKey(msg.id), pending);
  if (!writeToBackend(msg)) {
    inFlightClientRequests.delete(idKey(msg.id));
    writeToHost({
      jsonrpc: '2.0',
      id: msg.id,
      error: { code: -32603, message: 'compose-preview-mcp backend pipe closed' },
    });
  }
}

// -- Host stdio loop ------------------------------------------------------------------------------

let stdinBuffer = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (chunk) => {
  stdinBuffer += chunk;
  let nl;
  while ((nl = stdinBuffer.indexOf('\n')) !== -1) {
    const line = stdinBuffer.slice(0, nl).replace(/\r$/, '');
    stdinBuffer = stdinBuffer.slice(nl + 1);
    if (!line.trim()) continue;
    let msg;
    try {
      msg = JSON.parse(line);
    } catch {
      continue;
    }
    handleClientMessage(msg);
  }
});

let shutdownStarted = false;
function shutdownAndExit(reason) {
  if (shutdownStarted) return;
  shutdownStarted = true;
  hostClosed = true;
  stopBackend(reason, { waitForExit: true }).finally(() => {
    process.exit(0);
  });
}

process.stdin.on('end', () => shutdownAndExit('host-eof'));

for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, () => shutdownAndExit(sig));
}
process.on('exit', () => {
  const proc = backend || stoppingBackend;
  if (proc) {
    try {
      proc.kill('SIGTERM');
    } catch {
      // ignore
    }
  }
});
