#!/usr/bin/env node
// Antigravity sidecar launcher for Compose Preview (`browse`, `ui-builder`, and `launch --adb`).
//
// Listens immediately on 127.0.0.1:$ANTIGRAVITY_SIDECAR_WEB_PORT so the Auxiliary Pane never hits
// a connection error while Gradle or the preview server warms up, and stays idle (zero JVM cost)
// until the user or agent opens the pane. When `compose-preview` is not installed yet or the
// workspace has no Gradle/Bazel/Buck build, it serves a self-healing setup and mode-switcher page.

import { spawn } from 'node:child_process';
import { accessSync, constants, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import http from 'node:http';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { URL } from 'node:url';

const MODES = new Set(['browse', 'ui-builder', 'simulator']);
const initialModeArg = process.argv[2] || process.env.COMPOSE_PREVIEW_SIDECAR_MODE || 'browse';
let activeMode = MODES.has(initialModeArg) ? initialModeArg : 'browse';

const port = Number(process.env.ANTIGRAVITY_SIDECAR_WEB_PORT || process.env.PORT || 0);
if (!port) {
  process.stderr.write('ANTIGRAVITY_SIDECAR_WEB_PORT is not set\n');
  process.exit(1);
}

const INSTALL_CMD =
  'curl -fsSL https://raw.githubusercontent.com/yschimke/skills/main/scripts/install.sh | bash';
const MAX_LOG_LINES = 60;

function isExecutable(filePath) {
  try {
    accessSync(filePath, constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

function findCli() {
  const explicit = process.env.COMPOSE_PREVIEW_CLI;
  if (explicit && isExecutable(explicit)) {
    return explicit;
  }
  const pathDirs = (process.env.PATH || '').split(path.delimiter).filter(Boolean);
  for (const dir of pathDirs) {
    const candidate = path.join(dir, 'compose-preview');
    if (isExecutable(candidate)) {
      return candidate;
    }
  }
  const home = os.homedir();
  const fallbacks = [
    path.join(home, '.local', 'bin', 'compose-preview'),
    '/opt/homebrew/bin/compose-preview',
    '/usr/local/bin/compose-preview',
  ];
  for (const candidate of fallbacks) {
    if (isExecutable(candidate)) {
      return candidate;
    }
  }
  return null;
}

let workspaceOverride = '';

function cleanWorkspaceCandidate(raw) {
  if (!raw || typeof raw !== 'string') return null;
  const trimmed = raw.trim().replace(/^file:\/\//, '');
  if (!trimmed) return null;
  try {
    const resolved = path.resolve(trimmed);
    if (existsSync(resolved)) return resolved;
  } catch {
    // ignore invalid path
  }
  return null;
}

function parseWorkspaceList(raw) {
  if (!raw || typeof raw !== 'string') return null;
  const trimmed = raw.trim();
  if (trimmed.startsWith('[')) {
    try {
      const parsed = JSON.parse(trimmed);
      if (Array.isArray(parsed)) {
        for (const item of parsed) {
          const candidate =
            typeof item === 'string' ? item : item && (item.uri || item.path || item.fsPath);
          const valid = cleanWorkspaceCandidate(candidate);
          if (valid) return valid;
        }
      }
    } catch {
      // fall through to delimiter split
    }
  }
  for (const part of trimmed.split(path.delimiter)) {
    const valid = cleanWorkspaceCandidate(part);
    if (valid) return valid;
  }
  return null;
}

function workspaceCacheFile() {
  const cacheBase = process.env.XDG_CACHE_HOME || path.join(os.homedir(), '.cache');
  return path.join(cacheBase, 'composeai', 'antigravity-workspace');
}

function mcpWorkspacesFile() {
  const cacheBase = process.env.XDG_CACHE_HOME || path.join(os.homedir(), '.cache');
  return path.join(cacheBase, 'composeai', 'mcp', 'workspaces.json');
}

function readRecentMcpWorkspaces() {
  try {
    const file = mcpWorkspacesFile();
    if (!existsSync(file)) return [];
    const parsed = JSON.parse(readFileSync(file, 'utf8'));
    const list = Array.isArray(parsed?.workspaces) ? parsed.workspaces : [];
    const sorted = [...list].sort((a, b) => Number(b?.lastUsed || 0) - Number(a?.lastUsed || 0));
    const results = [];
    const seen = new Set();
    for (const entry of sorted) {
      const valid = cleanWorkspaceCandidate(entry?.path);
      if (valid && !seen.has(valid) && detectBuildProject(valid)) {
        seen.add(valid);
        results.push(valid);
      }
    }
    return results;
  } catch {
    return [];
  }
}

function persistWorkspaceOverride(dir) {
  const valid = cleanWorkspaceCandidate(dir);
  if (!valid) return null;
  workspaceOverride = valid;
  try {
    const file = workspaceCacheFile();
    mkdirSync(path.dirname(file), { recursive: true });
    writeFileSync(file, `${valid}\n`, 'utf8');
  } catch {
    // ignore cache write errors
  }
  return valid;
}

function resolveWorkspace() {
  const override = cleanWorkspaceCandidate(workspaceOverride);
  if (override) return override;

  for (const key of [
    'COMPOSE_PREVIEW_WORKSPACE',
    'ANTIGRAVITY_WORKSPACE_PATH',
    'ANTIGRAVITY_WORKSPACE_ROOT',
    'WORKSPACE_PATH',
    'WORKSPACE_FOLDER',
    'VSCODE_WORKSPACE_FOLDER',
    'VSCODE_CWD',
    'PROJECT_ROOT',
    'INIT_CWD',
  ]) {
    const candidate = cleanWorkspaceCandidate(process.env[key]);
    if (candidate) return candidate;
  }

  for (const listKey of ['ANTIGRAVITY_WORKSPACE_PATHS', 'WORKSPACE_FOLDER_PATHS']) {
    const candidate = parseWorkspaceList(process.env[listKey]);
    if (candidate) return candidate;
  }

  if (detectBuildProject(process.cwd())) {
    return process.cwd();
  }

  try {
    const cacheFile = workspaceCacheFile();
    if (existsSync(cacheFile)) {
      const cached = cleanWorkspaceCandidate(readFileSync(cacheFile, 'utf8'));
      if (cached) return cached;
    }
  } catch {
    // ignore cache read errors
  }

  const recentMcp = readRecentMcpWorkspaces();
  if (recentMcp.length > 0) {
    return recentMcp[0];
  }

  return process.cwd();
}

function detectBuildProject(dir) {
  let current = path.resolve(dir);
  for (let i = 0; i < 6; i++) {
    for (const marker of [
      'settings.gradle.kts',
      'settings.gradle',
      'gradlew',
      'MODULE.bazel',
      'WORKSPACE',
      '.buckconfig',
    ]) {
      if (existsSync(path.join(current, marker))) {
        return current;
      }
    }
    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }
  return null;
}

function allocateFreePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.on('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const addr = srv.address();
      const found = typeof addr === 'object' && addr ? addr.port : 0;
      srv.close(() => resolve(found));
    });
  });
}

function probePort(targetPort) {
  return new Promise((resolve) => {
    const socket = net.connect({ host: '127.0.0.1', port: targetPort });
    socket.setTimeout(400);
    socket.on('connect', () => {
      socket.destroy();
      resolve(true);
    });
    socket.on('timeout', () => {
      socket.destroy();
      resolve(false);
    });
    socket.on('error', () => {
      socket.destroy();
      resolve(false);
    });
  });
}

let childProc = null;
let backendPort = null;
let state = 'idle'; // 'idle' | 'missing-cli' | 'no-project' | 'starting' | 'ready' | 'failed' | 'stopped'
let lastError = '';
let adbSerial = null;
let grpcPort = null;
const logLines = [];

function pushLog(text) {
  for (const raw of String(text).split(/\r?\n/)) {
    const line = raw.trimEnd();
    if (!line) continue;
    logLines.push(line);
    if (logLines.length > MAX_LOG_LINES) {
      logLines.shift();
    }
    const adbMatch = line.match(/device\s+(emulator-\d+)/);
    if (adbMatch) {
      adbSerial = adbMatch[1];
    }
    const grpcMatch = line.match(/emulator gRPC on (\d+)/);
    if (grpcMatch) {
      grpcPort = Number(grpcMatch[1]);
    }
    try {
      if (line.startsWith('{') && line.endsWith('}')) {
        const evt = JSON.parse(line);
        if (evt.event === 'device') {
          if (evt.serial) adbSerial = evt.serial;
          if (evt.grpcPort) grpcPort = evt.grpcPort;
        }
      }
    } catch {
      // ignore non-JSON log lines
    }
  }
}

function stopChild() {
  if (childProc) {
    const proc = childProc;
    childProc = null;
    try {
      proc.kill('SIGTERM');
    } catch {
      // ignore
    }
  }
  backendPort = null;
  adbSerial = null;
  grpcPort = null;
}

async function startBackend(requestedMode = activeMode) {
  activeMode = MODES.has(requestedMode) ? requestedMode : 'browse';
  stopChild();
  logLines.length = 0;
  lastError = '';

  const cli = findCli();
  if (!cli) {
    state = 'missing-cli';
    return;
  }

  const workspace = resolveWorkspace();
  const projectRoot = detectBuildProject(workspace);
  if (!projectRoot && activeMode !== 'simulator') {
    state = 'no-project';
    return;
  }

  const cwd = projectRoot || workspace;
  let args = [];

  if (activeMode === 'browse') {
    backendPort = await allocateFreePort();
    args = ['browse', '--host', '127.0.0.1', '--port', String(backendPort), '--public', '--no-open'];
  } else if (activeMode === 'ui-builder') {
    backendPort = await allocateFreePort();
    args = ['ui-builder', '--host', '127.0.0.1', '--port', String(backendPort), '--no-open'];
  } else if (activeMode === 'simulator') {
    backendPort = null;
    args = projectRoot
      ? ['launch', '--project', projectRoot, '--adb', '--control', 'stdio']
      : ['launch', '--adb', '--control', 'stdio'];
  }

  state = 'starting';
  pushLog(`$ ${cli} ${args.join(' ')}`);

  const env = {
    ...process.env,
    PATH: [path.dirname(cli), process.env.PATH].filter(Boolean).join(path.delimiter),
  };

  const proc = spawn(cli, args, {
    cwd,
    env,
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  childProc = proc;

  proc.stdout.on('data', (chunk) => {
    pushLog(chunk);
    if (activeMode === 'simulator' && adbSerial) {
      state = 'ready';
    }
  });
  proc.stderr.on('data', (chunk) => {
    pushLog(chunk);
    if (activeMode === 'simulator' && adbSerial) {
      state = 'ready';
    }
  });
  proc.on('error', (err) => {
    if (childProc !== proc) return;
    lastError = err.message;
    state = 'failed';
    childProc = null;
  });
  proc.on('exit', (code, signal) => {
    if (childProc !== proc) return;
    childProc = null;
    if (state !== 'stopped') {
      lastError = code ? `compose-preview exited with code ${code}` : `stopped (${signal || 'exit'})`;
      state = 'failed';
    }
  });

  if (backendPort) {
    pollBackendPort(proc, backendPort);
  }
}

async function pollBackendPort(proc, targetPort) {
  while (childProc === proc && state === 'starting') {
    // eslint-disable-next-line no-await-in-loop
    const up = await probePort(targetPort);
    if (childProc !== proc) return;
    if (up) {
      state = 'ready';
      return;
    }
    // eslint-disable-next-line no-await-in-loop
    await new Promise((r) => setTimeout(r, 350));
  }
}

function getStatusPayload() {
  const cli = findCli();
  const workspace = resolveWorkspace();
  const projectRoot = detectBuildProject(workspace);
  const recentWorkspaces = readRecentMcpWorkspaces().slice(0, 5);
  return {
    ok: state === 'ready',
    mode: activeMode,
    state,
    cliPath: cli,
    workspace,
    projectRoot,
    recentWorkspaces,
    hasProject: Boolean(projectRoot),
    backendPort,
    adbSerial,
    grpcPort,
    lastError,
    logs: logLines,
  };
}

function escapeHtml(str) {
  return String(str)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function renderControlPage() {
  const status = getStatusPayload();
  const titleByMode = {
    browse: 'Component Browser',
    'ui-builder': 'Compose UI Builder',
    simulator: 'Robolectric Simulator (--adb)',
  };
  const logText = status.logs.length
    ? escapeHtml(status.logs.slice(-25).join('\n'))
    : 'Waiting for output…';

  let bodySection = '';
  if (status.state === 'missing-cli') {
    bodySection = `
      <h2><code>compose-preview</code> CLI not found</h2>
      <p>Install the Compose Preview CLI so Antigravity can render <code>@Preview</code> composables, open the UI Builder, and run the Robolectric simulator:</p>
      <pre>${escapeHtml(INSTALL_CMD)}</pre>
      <div class="actions">
        <button class="primary" onclick="switchMode('${escapeHtml(status.mode)}')">Retry</button>
      </div>`;
  } else if (status.state === 'no-project') {
    const recentButtons = (status.recentWorkspaces || [])
      .map(
        (w) =>
          `<button onclick="selectWorkspace('${escapeHtml(w)}')">${escapeHtml(path.basename(w))}</button>`,
      )
      .join('');
    bodySection = `
      <h2>No Compose / Gradle project detected</h2>
      <p>Checked <code>${escapeHtml(status.workspace)}</code> for <code>settings.gradle(.kts)</code>, <code>gradlew</code>, <code>MODULE.bazel</code>, or <code>.buckconfig</code>.</p>
      <p>Enter your Compose project directory below, or boot a standalone Robolectric virtual device on <code>adb</code> for the Android Device Hub:</p>
      <div class="actions" style="margin-bottom: 12px;">
        <input id="workspaceInput" type="text" value="${escapeHtml(status.workspace)}" placeholder="/path/to/your/compose-project" style="flex: 1; min-width: 240px; padding: 6px 10px; border-radius: 6px; border: 1px solid var(--border); background: var(--card); color: var(--fg); font: inherit;" />
        <button class="primary" onclick="setWorkspace()">Use Workspace</button>
      </div>
      ${recentButtons ? `<div class="actions" style="margin-bottom: 12px;">${recentButtons}</div>` : ''}
      <div class="actions">
        <button onclick="switchMode('simulator')">Boot Simulator (<code>launch --adb</code>)</button>
        <button onclick="switchMode('browse')">Retry Project Discovery</button>
      </div>`;
  } else if (status.state === 'simulator' || status.mode === 'simulator') {
    const deviceReady = status.state === 'ready' && status.adbSerial;
    bodySection = `
      <h2>${deviceReady ? `Simulator running on <code>${escapeHtml(status.adbSerial)}</code>` : 'Starting Robolectric Simulator…'}</h2>
      <p>${
        deviceReady
          ? `Registered with <code>adb</code> as <code>${escapeHtml(status.adbSerial)}</code>${
              status.grpcPort ? ` (emulator gRPC port <code>${status.grpcPort}</code>)` : ''
            }. Open <strong>Android Device Hub</strong> or run <code>adb devices</code> to mirror and interact with the device.`
          : 'Converting APK / provisioning Robolectric virtual device…'
      }</p>
      <pre id="logs">${logText}</pre>
      <div class="actions">
        <button class="primary" onclick="switchMode('simulator')">Restart Simulator</button>
        <button onclick="switchMode('browse')">Switch to Component Browser</button>
        <button onclick="switchMode('ui-builder')">Switch to UI Builder</button>
      </div>`;
  } else if (status.state === 'failed') {
    bodySection = `
      <h2>${escapeHtml(titleByMode[status.mode] || 'Compose Preview')} stopped</h2>
      <p class="error">${escapeHtml(status.lastError || 'Process exited unexpectedly.')}</p>
      <pre id="logs">${logText}</pre>
      <div class="actions">
        <button class="primary" onclick="switchMode('${escapeHtml(status.mode)}')">Retry</button>
        <button onclick="switchMode('browse')">Component Browser</button>
        <button onclick="switchMode('ui-builder')">UI Builder</button>
        <button onclick="switchMode('simulator')">Simulator (<code>--adb</code>)</button>
      </div>`;
  } else {
    bodySection = `
      <h2>Starting ${escapeHtml(titleByMode[status.mode] || 'Compose Preview')}…</h2>
      <p>Discovering <code>@Preview</code> functions in <code>${escapeHtml(status.projectRoot || status.workspace)}</code>. This pane will open automatically as soon as the server is ready.</p>
      <pre id="logs">${logText}</pre>
      <div class="actions">
        <button onclick="switchMode('browse')">Component Browser</button>
        <button onclick="switchMode('ui-builder')">UI Builder</button>
        <button onclick="switchMode('simulator')">Simulator (<code>--adb</code>)</button>
      </div>`;
  }

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Compose Preview</title>
<style>
  :root {
    --fg: #e3e3e3; --muted: #9aa0a6; --bg: #18181b;
    --card: #222327; --border: #34363c; --accent: #3ddc84; --err: #f28b82;
  }
  @media (prefers-color-scheme: light) {
    :root {
      --fg: #1f1f1f; --muted: #5f6368; --bg: #ffffff;
      --card: #f6f8fa; --border: #dadce0; --accent: #1b873f; --err: #c5221f;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 20px; min-height: 100vh;
    font: 13px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: var(--fg); background: var(--bg);
  }
  .header {
    display: flex; align-items: center; justify-content: space-between;
    gap: 8px; padding-bottom: 12px; margin-bottom: 16px;
    border-bottom: 1px solid var(--border);
  }
  .brand { font-weight: 600; font-size: 14px; display: flex; align-items: center; gap: 8px; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); display: inline-block; }
  .tabs { display: flex; gap: 6px; flex-wrap: wrap; }
  h2 { font-size: 15px; font-weight: 600; margin: 0 0 8px; }
  p { margin: 0 0 12px; color: var(--muted); }
  p.error { color: var(--err); }
  code, pre { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
  pre {
    padding: 10px 12px; border-radius: 6px; overflow: auto; max-height: 260px;
    background: var(--card); border: 1px solid var(--border);
    white-space: pre-wrap; word-break: break-word; margin: 0 0 14px;
  }
  .actions { display: flex; gap: 8px; flex-wrap: wrap; }
  button {
    padding: 6px 12px; border-radius: 6px; cursor: pointer;
    font: inherit; color: var(--fg); background: var(--card);
    border: 1px solid var(--border);
  }
  button.primary { border-color: var(--accent); font-weight: 500; }
  button:hover { filter: brightness(1.1); }
</style>
</head>
<body>
  <div class="header">
    <div class="brand"><span class="dot"></span>Compose Preview</div>
    <div class="tabs">
      <button onclick="switchMode('browse')">Browse</button>
      <button onclick="switchMode('ui-builder')">UI Builder</button>
      <button onclick="switchMode('simulator')">Simulator</button>
    </div>
  </div>
  ${bodySection}
<script>
async function switchMode(mode) {
  await fetch('/__sidecar/mode?mode=' + encodeURIComponent(mode), { method: 'POST' });
  location.reload();
}
async function setWorkspace() {
  const input = document.getElementById('workspaceInput');
  if (!input || !input.value.trim()) return;
  await selectWorkspace(input.value.trim());
}
async function selectWorkspace(dir) {
  await fetch('/__sidecar/workspace?workspace=' + encodeURIComponent(dir), { method: 'POST' });
  location.reload();
}
setInterval(async () => {
  try {
    const res = await fetch('/__sidecar/status', { cache: 'no-store' });
    const data = await res.json();
    const logsEl = document.getElementById('logs');
    if (logsEl && Array.isArray(data.logs) && data.logs.length) {
      logsEl.textContent = data.logs.slice(-25).join('\\n');
      logsEl.scrollTop = logsEl.scrollHeight;
    }
    if (data.state === 'ready' && data.backendPort) {
      location.reload();
    }
  } catch {}
}, 1000);
</script>
</body>
</html>`;
}

const server = http.createServer(async (req, res) => {
  const reqUrl = new URL(req.url || '/', `http://127.0.0.1:${port}`);
  const queryWorkspace = reqUrl.searchParams.get('workspace');
  if (queryWorkspace) {
    persistWorkspaceOverride(queryWorkspace);
  }

  if (reqUrl.pathname === '/__sidecar/status') {
    const payload = JSON.stringify(getStatusPayload(), null, 2);
    res.writeHead(200, {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
    });
    res.end(payload);
    return;
  }

  if (reqUrl.pathname === '/__sidecar/workspace') {
    const requestedWorkspace = reqUrl.searchParams.get('workspace') || '';
    const updated = persistWorkspaceOverride(requestedWorkspace);
    if (updated) {
      await startBackend(activeMode);
    }
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify(getStatusPayload()));
    return;
  }

  if (reqUrl.pathname === '/__sidecar/mode') {
    const requested = reqUrl.searchParams.get('mode') || 'browse';
    if (requested === 'stop') {
      stopChild();
      state = 'stopped';
    } else {
      await startBackend(requested);
    }
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify(getStatusPayload()));
    return;
  }

  // Lazy start on first user/pane navigation so idle workspaces pay zero JVM cost.
  if (state === 'idle') {
    await startBackend(activeMode);
  }

  if (state === 'ready' && backendPort) {
    const proxyReq = http.request(
      {
        hostname: '127.0.0.1',
        port: backendPort,
        path: req.url,
        method: req.method,
        headers: { ...req.headers, host: `127.0.0.1:${backendPort}` },
      },
      (proxyRes) => {
        res.writeHead(proxyRes.statusCode || 502, proxyRes.headers);
        proxyRes.pipe(res);
      },
    );
    proxyReq.on('error', () => {
      res.writeHead(200, {
        'Content-Type': 'text/html; charset=utf-8',
        'Cache-Control': 'no-store',
      });
      res.end(renderControlPage());
    });
    req.pipe(proxyReq);
    return;
  }

  const html = renderControlPage();
  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store',
  });
  res.end(html);
});

server.on('upgrade', (req, socket, head) => {
  if (state !== 'ready' || !backendPort) {
    socket.destroy();
    return;
  }
  const upstream = net.connect(backendPort, '127.0.0.1', () => {
    const lines = [`${req.method} ${req.url} HTTP/${req.httpVersion}`];
    for (let i = 0; i < req.rawHeaders.length; i += 2) {
      const k = req.rawHeaders[i];
      const v = req.rawHeaders[i + 1];
      if (k.toLowerCase() === 'host') {
        lines.push(`Host: 127.0.0.1:${backendPort}`);
      } else {
        lines.push(`${k}: ${v}`);
      }
    }
    lines.push('', '');
    upstream.write(lines.join('\r\n'));
    if (head && head.length) upstream.write(head);
    socket.pipe(upstream).pipe(socket);
  });
  upstream.on('error', () => socket.destroy());
  socket.on('error', () => upstream.destroy());
});

for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, () => {
    stopChild();
    process.exit(0);
  });
}
process.on('exit', () => stopChild());

server.listen(port, '127.0.0.1');
