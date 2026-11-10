#!/usr/bin/env python3
"""Dependency-free stdio MCP server used by the harness compatibility spike."""

from __future__ import annotations

import json
import os
import sys
from itertools import count
from pathlib import Path


PIXEL = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/"
    "S+xHAAAAAElFTkSuQmCC"
)
VIEWER_URI = "ui://spike/app"
VIEWER_MIME_TYPE = "text/html;profile=mcp-app"
VIEWER_ICON_SVG = (
    "data:image/svg+xml,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' width='20' height='20' "
    "viewBox='0 0 20 20' fill='none' stroke='currentColor' stroke-width='1.5'%3E"
    "%3Crect x='3' y='2.5' width='14' height='15' rx='2'/%3E"
    "%3Cpath d='M6.5 7h7M6.5 10.5h7M6.5 14h4'/%3E"
    "%3C/svg%3E"
)
VIEWER_RESOURCE_META = {
    "ui": {"prefersBorder": True},
    "openai/ui": {
        "availableDisplayModes": ["inline", "fullscreen"],
        "preferredDisplayMode": "inline",
    },
}
SERVER_NAME = sys.argv[1] if len(sys.argv) == 2 else "unnamed"
LOG_PATH = Path(os.environ.get("SPIKE_LOG_PATH", f"/tmp/spike-{os.getpid()}.json"))
DETECTION_ENV_KEYS = (
    "ANTIGRAVITY_CLI_ALIAS",
    "ANTIGRAVITY_CONVERSATION_ID",
    "ANTIGRAVITY_WORKSPACE_PATH",
    "ANTIGRAVITY_WORKSPACE_ROOT",
    "CLAUDECODE",
    "CLAUDE_PLUGIN_ROOT",
    "CODEX_THREAD_ID",
    "CURSOR_TRACE_ID",
    "GEMINI_CLI",
    "OPENCODE",
    "__CFBundleIdentifier",
)
MAX_LOGGED_EVENTS = 200
SESSION_INITIALIZED = False
SESSION_LOG: dict[str, object] = {
    "serverName": SERVER_NAME,
    "protocolVersion": None,
    "clientInfo": None,
    "capabilities": None,
    "mcpAppsExtension": None,
    "environmentKeys": sorted(os.environ),
    "detectionEnvironment": {},
    "events": [],
    "viewerReports": [],
}
PENDING_ELICITATIONS: dict[object, object] = {}
ELICITATION_IDS = count(1)
CLIENT_ELICITATION_CAPABILITIES: dict[str, object] = {}
CLIENT_ELICITATION_DECLARED = False
FORM_FALLBACK = (
    "form elicitation unavailable; choose a variant in text: compact or expanded."
)
URL_FALLBACK = (
    "url elicitation unavailable; open https://example.invalid/spike-elicitation, "
    "enter verification code SPIKE-CODE, then call access_status until it reports authorized."
)

VIEWER_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Spike echo viewer</title>
<style>
  :root { color-scheme: light dark; font: 13px/1.45 system-ui, sans-serif; }
  body { margin: 0; padding: 12px; display: grid; gap: 10px; }
  section { border: 1px solid rgba(127, 127, 127, 0.35); border-radius: 6px; padding: 10px; }
  h2 { margin: 0 0 6px; font-size: 13px; }
  p { margin: 0 0 6px; }
  .row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 6px; }
  input, textarea {
    font: 12px/1.4 ui-monospace, monospace;
    padding: 4px 6px;
    border: 1px solid rgba(127, 127, 127, 0.45);
    border-radius: 4px;
    background: transparent;
    color: inherit;
  }
  input { flex: 1 1 220px; }
  textarea { width: 100%; box-sizing: border-box; min-height: 68px; margin-top: 6px; }
  button { font: inherit; padding: 4px 9px; cursor: pointer; }
  pre {
    margin: 6px 0 0;
    padding: 8px;
    max-height: 240px;
    overflow: auto;
    border-radius: 4px;
    background: rgba(127, 127, 127, 0.12);
    font: 11px/1.4 ui-monospace, monospace;
    white-space: pre-wrap;
    word-break: break-word;
  }
  [hidden] { display: none !important; }
</style>
</head>
<body>
<section>
  <h2>MCP Apps bridge</h2>
  <p id="status">Echo viewer ready. If this app is unavailable, use the text result.</p>
  <div class="row">
    <button id="action" type="button">Send viewer action</button>
    <button id="sync-report" type="button">Save report to spike log</button>
    <button id="copy-report" type="button">Copy report JSON</button>
  </div>
</section>

<section id="file-section">
  <h2>File viewer &amp; local write-back probe (.uid / .rc)</h2>
  <p id="file-status">Waiting for file tool-input, or enter a resourceUri to probe.</p>
  <div class="row">
    <input id="file-name" type="text" placeholder="sample.uid" aria-label="File name">
    <input id="file-uri" type="text" placeholder="file:///path/to/sample.uid" aria-label="File resourceUri">
  </div>
  <div class="row">
    <button id="read-file" type="button">1. Read file (resources/read)</button>
    <button id="subscribe-file" type="button">2. Subscribe + echo host _meta</button>
    <button id="arm-write" type="button">3. Save local file…</button>
    <button id="confirm-write" type="button" hidden>Confirm save to local file</button>
  </div>
  <textarea id="write-text" aria-label="Content to write back" placeholder="Read a file first or enter text to write back."></textarea>
</section>

<section>
  <h2>Observed report</h2>
  <pre id="report">{}</pre>
</section>

<script>
// Host-neutral JSON-RPC postMessage bridge. Server actions always return text too.
const pending = new Map();
let nextId = 1;
let initialized = false;
let resolvedTools = null;
let lastReadEtag = null;

const report = {
  userAgent: navigator.userAgent,
  locationHref: String(location.href),
  initialize: null,
  toolInput: null,
  toolInputPartialCount: 0,
  toolResult: null,
  hostContextChanges: [],
  resourceUpdates: [],
  otherNotifications: [],
  viewerAction: null,
  file: {
    name: null,
    uri: null,
    read: null,
    subscribe: null,
    serverEcho: null,
    writeAttempts: []
  }
};

function renderReport() {
  document.getElementById("report").textContent = JSON.stringify(report, null, 2);
}

function setFileCandidate(file) {
  if (!file || typeof file !== "object") return;
  const uri = typeof file.resourceUri === "string" ? file.resourceUri : (typeof file.uri === "string" ? file.uri : "");
  const name = typeof file.name === "string" ? file.name : "";
  if (uri) {
    document.getElementById("file-uri").value = uri;
    report.file.uri = uri;
  }
  if (name) {
    document.getElementById("file-name").value = name;
    report.file.name = name;
  }
  if (uri || name) {
    document.getElementById("file-status").textContent =
      `File input received: ${name || "(unnamed)"} (${uri || "no uri"})`;
  }
}

function prepareWriteCandidate(text) {
  if (typeof text !== "string") return "";
  try {
    const parsed = JSON.parse(text);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      parsed._spikeSavedAt = new Date().toISOString();
      return JSON.stringify(parsed, null, 2) + "\\n";
    }
  } catch (_ignored) {
    // Non-JSON file (such as .rc or plain text); append a trailing probe line.
  }
  return text.endsWith("\\n") ? `${text}# spike-saved\\n` : `${text}\\n# spike-saved\\n`;
}

function request(method, params) {
  const id = nextId++;
  window.parent.postMessage({jsonrpc: "2.0", id, method, params}, "*");
  return new Promise((resolve, reject) => pending.set(id, {resolve, reject}));
}

function notify(method, params) {
  window.parent.postMessage({jsonrpc: "2.0", method, params}, "*");
}

async function resolveToolName(baseName) {
  if (!resolvedTools) {
    try {
      const listed = await request("tools/list", {});
      resolvedTools = Array.isArray(listed?.tools) ? listed.tools.map(tool => tool.name) : [];
    } catch (_error) {
      resolvedTools = [];
    }
  }
  if (resolvedTools.includes(baseName)) return baseName;
  const match = resolvedTools.find(
    name =>
      name.endsWith(`:${baseName}`) ||
      name.endsWith(`__${baseName}`) ||
      name.endsWith(`_${baseName}`) ||
      name.endsWith(`.${baseName}`)
  );
  return match || baseName;
}

async function callServerTool(baseName, args) {
  try {
    return await request("tools/call", {name: baseName, arguments: args});
  } catch (firstError) {
    const resolved = await resolveToolName(baseName);
    if (resolved !== baseName) {
      return await request("tools/call", {name: resolved, arguments: args});
    }
    throw firstError;
  }
}

async function syncReport(trigger, extraArgs = {}) {
  renderReport();
  if (!initialized) return null;
  try {
    const payload = {
      report: {...report, lastTrigger: trigger},
      ...extraArgs
    };
    const response = await callServerTool("viewer_report", payload);
    return response;
  } catch (error) {
    report.reportSyncError = {trigger, error};
    renderReport();
    return null;
  }
}

window.addEventListener("message", event => {
  if (event.source !== window.parent) return;
  const message = event.data;
  if (!message || message.jsonrpc !== "2.0") return;
  if (pending.has(message.id)) {
    const pendingRequest = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) {
      pendingRequest.reject(message.error);
      return;
    }
    pendingRequest.resolve(message.result);
    return;
  }
  if (typeof message.method === "string") {
    const params = message.params ?? null;
    if (message.method === "ui/notifications/tool-input") {
      report.toolInput = params;
      setFileCandidate(params?.arguments?.file);
      void syncReport("tool-input");
    } else if (message.method === "ui/notifications/tool-input-partial") {
      report.toolInputPartialCount += 1;
      setFileCandidate(params?.arguments?.file);
      renderReport();
    } else if (message.method === "ui/notifications/tool-result") {
      report.toolResult = {
        isError: Boolean(params?.isError),
        contentTypes: Array.isArray(params?.content) ? params.content.map(item => item?.type) : [],
        structuredContent: params?.structuredContent ?? null,
        meta: params?._meta ?? null
      };
      setFileCandidate(params?.structuredContent?.file);
      void syncReport("tool-result");
    } else if (message.method === "ui/notifications/host-context-changed") {
      report.hostContextChanges.push(params);
      setFileCandidate(params?.file);
      void syncReport("host-context-changed");
    } else if (
      message.method === "notifications/resources/updated" ||
      message.method === "ui/notifications/resource-updated"
    ) {
      report.resourceUpdates.push({method: message.method, params});
      void syncReport("resource-updated");
    } else {
      report.otherNotifications.push({method: message.method, params});
      void syncReport("other-notification");
    }
  }
}, {passive: true});

async function initializeBridge() {
  try {
    const initResult = await request("ui/initialize", {
      appInfo: {name: "spike-echo-viewer", version: "0.2.0"},
      appCapabilities: {availableDisplayModes: ["inline", "fullscreen"]},
      protocolVersion: "2026-01-26"
    });
    initialized = true;
    report.initialize = initResult;
    setFileCandidate(initResult?.hostContext?.file || initResult?.hostContext);
    notify("ui/notifications/initialized", {});
    const hostName = initResult?.hostInfo?.name || "host";
    document.getElementById("status").textContent =
      `Bridge initialized with ${hostName}.`;
    await syncReport("initialized");
  } catch (error) {
    report.initialize = {error};
    renderReport();
    document.getElementById("status").textContent = "Viewer unavailable; use the text fallback.";
    console.error("Failed to initialize the MCP Apps bridge:", error);
  }
}

renderReport();
const bridgeReady = initializeBridge();

document.getElementById("action").addEventListener("click", async () => {
  await bridgeReady;
  if (!initialized) {
    document.getElementById("status").textContent = "Viewer unavailable; use the text fallback.";
    return;
  }
  try {
    let response;
    try {
      response = await request("tools/call", {name: "status", arguments: {}});
    } catch (_directError) {
      response = await callServerTool("status", {});
    }
    await request("ui/message", {
      role: "user",
      content: {type: "text", text: "Spike viewer requested status."}
    });
    const statusText = response.content?.[0]?.text || "Status requested; use the text fallback.";
    report.viewerAction = {ok: true, statusText};
    document.getElementById("status").textContent = statusText;
    await syncReport("viewer-action");
  } catch (error) {
    report.viewerAction = {ok: false, error};
    document.getElementById("status").textContent = "Status unavailable; use the text fallback.";
    await syncReport("viewer-action-error");
    console.error("Viewer action failed:", error);
  }
});

document.getElementById("sync-report").addEventListener("click", async () => {
  await bridgeReady;
  const response = await syncReport("manual-save");
  const logPath = response?.structuredContent?.logPath;
  document.getElementById("status").textContent =
    logPath ? `Saved viewer report to ${logPath}` : "Attempted report save; inspect report JSON.";
});

document.getElementById("copy-report").addEventListener("click", async () => {
  renderReport();
  try {
    await navigator.clipboard.writeText(document.getElementById("report").textContent);
    document.getElementById("status").textContent = "Copied report JSON to clipboard.";
  } catch (_error) {
    document.getElementById("status").textContent =
      "Clipboard unavailable in this iframe; copy from the Observed report block or /tmp/spike-*.json.";
  }
});

function currentFileInput() {
  const uri = document.getElementById("file-uri").value.trim();
  const name =
    document.getElementById("file-name").value.trim() ||
    (uri ? uri.split("/").pop() || "sample.uid" : "sample.uid");
  report.file.uri = uri || null;
  report.file.name = name || null;
  return {name, resourceUri: uri};
}

document.getElementById("read-file").addEventListener("click", async () => {
  await bridgeReady;
  const file = currentFileInput();
  if (!file.resourceUri) {
    document.getElementById("file-status").textContent = "Enter or open a file resourceUri first.";
    return;
  }
  try {
    const readResult = await request("resources/read", {uri: file.resourceUri});
    const content = readResult?.contents?.[0] || null;
    const meta = content?._meta || null;
    const openAiMeta = meta?.["openai/resource"] || null;
    lastReadEtag = openAiMeta?.etag || meta?.etag || null;
    const hasText = typeof content?.text === "string";
    const hasBlob = typeof content?.blob === "string";
    report.file.read = {
      ok: true,
      uri: content?.uri || file.resourceUri,
      mimeType: content?.mimeType || null,
      representation: hasText ? "text" : (hasBlob ? "blob" : "empty"),
      length: hasText ? content.text.length : (hasBlob ? content.blob.length : 0),
      meta,
      writable: openAiMeta?.writable ?? meta?.writable ?? null,
      etag: lastReadEtag
    };
    if (hasText) {
      document.getElementById("write-text").value = prepareWriteCandidate(content.text);
    }
    document.getElementById("file-status").textContent =
      `Read ${file.name}: ${report.file.read.representation} (${report.file.read.length} chars).`;
    await syncReport("file-read");
  } catch (error) {
    report.file.read = {ok: false, error};
    document.getElementById("file-status").textContent = "resources/read failed; see report JSON.";
    await syncReport("file-read-error");
  }
});

document.getElementById("subscribe-file").addEventListener("click", async () => {
  await bridgeReady;
  const file = currentFileInput();
  if (!file.resourceUri) {
    document.getElementById("file-status").textContent = "Enter or open a file resourceUri first.";
    return;
  }
  try {
    const subResult = await request("resources/subscribe", {uri: file.resourceUri});
    report.file.subscribe = {ok: true, result: subResult ?? {}};
  } catch (error) {
    report.file.subscribe = {ok: false, error};
  }
  const echoResponse = await syncReport("file-subscribe-and-touch", {
    file,
    touch: true
  });
  report.file.serverEcho = echoResponse?.structuredContent ?? null;
  document.getElementById("file-status").textContent =
    "Subscribed and probed server _meta echo; see report JSON.";
  renderReport();
});

document.getElementById("arm-write").addEventListener("click", () => {
  const writeBox = document.getElementById("write-text");
  if (!writeBox.value) {
    writeBox.value = JSON.stringify(
      {format: "spike-uid", _spikeSavedAt: new Date().toISOString()},
      null,
      2
    ) + "\\n";
  }
  document.getElementById("confirm-write").hidden = false;
  document.getElementById("file-status").textContent =
    "Review the text below, then click Confirm save to local file.";
});

document.getElementById("confirm-write").addEventListener("click", async () => {
  await bridgeReady;
  document.getElementById("confirm-write").hidden = true;
  const file = currentFileInput();
  if (!file.resourceUri) {
    document.getElementById("file-status").textContent = "Enter or open a file resourceUri first.";
    return;
  }
  const text = document.getElementById("write-text").value;
  const attempts = [];
  const candidates = [
    [
      "openai/resources/write",
      {uri: file.resourceUri, text, ...(lastReadEtag ? {ifMatch: lastReadEtag} : {})}
    ],
    ["resources/write", {uri: file.resourceUri, text}],
    ["ui/resources/write", {uri: file.resourceUri, text}]
  ];
  let succeededMethod = null;
  for (const [method, params] of candidates) {
    try {
      const writeResult = await request(method, params);
      attempts.push({method, ok: true, result: writeResult ?? {}});
      const nextEtag = writeResult?.etag || writeResult?._meta?.["openai/resource"]?.etag;
      if (nextEtag) lastReadEtag = nextEtag;
      succeededMethod = method;
      break;
    } catch (error) {
      attempts.push({method, ok: false, error});
      if (error && typeof error === "object" && error.code !== -32601) {
        // Method exists on the host, so stop probing fallback method names.
        break;
      }
    }
  }
  report.file.writeAttempts = attempts;
  document.getElementById("file-status").textContent = succeededMethod
    ? `Saved local file via ${succeededMethod}.`
    : "Local file write returned an error; see writeAttempts in report JSON.";
  await syncReport("file-write");
});
</script>
</body>
</html>
"""

FILE_INPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "resourceUri": {"type": "string"},
    },
    "required": ["name", "resourceUri"],
    "additionalProperties": False,
}

TOUCH_RESULT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "requested": {"type": "boolean"},
        "touched": {"type": "boolean"},
        "path": {"type": ["string", "null"]},
        "reason": {"type": "string"},
    },
    "required": ["requested", "touched"],
    "additionalProperties": False,
}

TOOLS = [
    {
        "name": "render_preview",
        "description": "Return the echo MCP server name and a 1×1 image, with a viewer resource and text fallback.",
        "inputSchema": {"type": "object", "additionalProperties": False},
        "outputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string"},
                "surface": {"type": "string", "enum": ["render_preview"]},
            },
            "required": ["server", "surface"],
            "additionalProperties": False,
        },
        "_meta": {
            "ui": {"resourceUri": VIEWER_URI, "visibility": ["model", "app"]},
            "ui/resourceUri": VIEWER_URI,
        },
    },
    {
        "name": "open_file",
        "title": "Spike Design Viewer",
        "description": "Open a .uid or .rc file in the spike MCP App viewer to probe file-viewer read, subscribe, and local save support.",
        "icons": [{"src": VIEWER_ICON_SVG, "mimeType": "image/svg+xml", "sizes": ["20x20"]}],
        "inputSchema": {
            "type": "object",
            "properties": {"file": FILE_INPUT_SCHEMA},
            "required": ["file"],
            "additionalProperties": False,
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string"},
                "surface": {"type": "string", "enum": ["open_file"]},
                "file": FILE_INPUT_SCHEMA,
                "requestMeta": {"type": ["object", "null"]},
            },
            "required": ["server", "surface", "file", "requestMeta"],
            "additionalProperties": False,
        },
        "_meta": {
            "ui": {"resourceUri": VIEWER_URI, "visibility": ["model", "app"]},
            "ui/resourceUri": VIEWER_URI,
            "openai/ui": {
                "entrypoints": [{"type": "file", "extensions": ["uid", "rc"]}],
            },
        },
    },
    {
        "name": "viewer_report",
        "description": "Record MCP App viewer diagnostics in the spike log and echo host _meta.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "report": {"type": "object"},
                "file": FILE_INPUT_SCHEMA,
                "touch": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string"},
                "logPath": {"type": "string"},
                "requestMeta": {"type": ["object", "null"]},
                "touched": TOUCH_RESULT_SCHEMA,
                "reportCount": {"type": "integer"},
            },
            "required": ["server", "logPath", "requestMeta", "touched", "reportCount"],
            "additionalProperties": False,
        },
        "_meta": {"ui": {"visibility": ["app"]}},
    },
    {
        "name": "status",
        "description": "Return the echo MCP server name.",
        "inputSchema": {"type": "object", "additionalProperties": False},
    },
    {
        "name": "access_status",
        "description": "Poll the fixture authorization flow until it is authorized.",
        "inputSchema": {"type": "object", "additionalProperties": False},
    },
    {
        "name": "ask",
        "description": "Probe form or URL elicitation and return text if the client declines or cannot elicit.",
        "inputSchema": {
            "type": "object",
            "properties": {"mode": {"type": "string", "enum": ["form", "url"]}},
            "required": ["mode"],
            "additionalProperties": False,
        },
    },
]
PROMPTS = [
    {
        "name": "spike-prompt",
        "description": "Fixture prompt that requests an echo preview for a file.",
        "arguments": [{"name": "path", "description": "A source file path", "required": True}],
    }
]


def flush_log() -> None:
    if not SESSION_INITIALIZED:
        return
    SESSION_LOG["serverName"] = SERVER_NAME
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(
        json.dumps(SESSION_LOG, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def record_event(entry: dict[str, object]) -> None:
    events = SESSION_LOG.get("events")
    if isinstance(events, list) and len(events) < MAX_LOGGED_EVENTS:
        events.append(entry)
    flush_log()


def log_initialize(params: object) -> None:
    global SESSION_INITIALIZED
    SESSION_INITIALIZED = True
    protocol_version = params.get("protocolVersion") if isinstance(params, dict) else None
    client_info = params.get("clientInfo") if isinstance(params, dict) else None
    capabilities = params.get("capabilities") if isinstance(params, dict) else None
    extensions = capabilities.get("extensions") if isinstance(capabilities, dict) else None
    mcp_apps_extension = (
        extensions.get("io.modelcontextprotocol/ui") if isinstance(extensions, dict) else None
    )
    request_meta = params.get("_meta") if isinstance(params, dict) else None
    SESSION_LOG.clear()
    SESSION_LOG.update(
        {
            "serverName": SERVER_NAME,
            "protocolVersion": protocol_version,
            "clientInfo": client_info,
            "capabilities": capabilities,
            "mcpAppsExtension": mcp_apps_extension,
            "environmentKeys": sorted(os.environ),
            "detectionEnvironment": {
                key: os.environ[key] for key in DETECTION_ENV_KEYS if key in os.environ
            },
            "events": [
                {
                    "method": "initialize",
                    "protocolVersion": protocol_version,
                    "meta": request_meta,
                }
            ],
            "viewerReports": [],
        }
    )
    flush_log()


def save_client_capabilities(params: object) -> None:
    global CLIENT_ELICITATION_CAPABILITIES, CLIENT_ELICITATION_DECLARED
    capabilities = params.get("capabilities") if isinstance(params, dict) else None
    elicitation = capabilities.get("elicitation") if isinstance(capabilities, dict) else None
    CLIENT_ELICITATION_DECLARED = isinstance(elicitation, dict)
    CLIENT_ELICITATION_CAPABILITIES = elicitation if isinstance(elicitation, dict) else {}


def supports_elicitation(mode: str) -> bool:
    if mode == "form":
        # Older clients advertised a bare `elicitation: {}` capability before
        # form/url sub-capabilities were standardized.
        return CLIENT_ELICITATION_DECLARED and (
            not CLIENT_ELICITATION_CAPABILITIES or "form" in CLIENT_ELICITATION_CAPABILITIES
        )
    return CLIENT_ELICITATION_DECLARED and "url" in CLIENT_ELICITATION_CAPABILITIES


def valid_file_input(value: object) -> dict[str, str] | None:
    if not isinstance(value, dict) or set(value) != {"name", "resourceUri"}:
        return None
    name = value.get("name")
    resource_uri = value.get("resourceUri")
    if not isinstance(name, str) or not name or not isinstance(resource_uri, str) or not resource_uri:
        return None
    return {"name": name, "resourceUri": resource_uri}


def extract_host_path(request_meta: object) -> str | None:
    if not isinstance(request_meta, dict):
        return None
    for namespace in ("openai/resource", "antigravity/resource", "resource"):
        nested = request_meta.get(namespace)
        if isinstance(nested, dict) and isinstance(nested.get("path"), str) and nested["path"]:
            return nested["path"]
    direct = request_meta.get("path")
    if isinstance(direct, str) and direct:
        return direct
    return None


def maybe_touch_probe_file(host_path: str | None, touch: bool) -> dict[str, object]:
    if not touch:
        return {"requested": False, "touched": False, "path": host_path}
    if not host_path:
        return {"requested": True, "touched": False, "reason": "no host path in _meta"}
    candidate = Path(host_path)
    if candidate.suffix.lower() not in {".uid", ".rc"}:
        return {"requested": True, "touched": False, "reason": "unsupported extension"}
    if candidate.is_symlink() or not candidate.is_file():
        return {"requested": True, "touched": False, "reason": "not a regular file"}
    os.utime(candidate, None)
    return {"requested": True, "touched": True, "path": str(candidate)}


def send(message: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def result(request_id: object, value: object) -> None:
    send({"jsonrpc": "2.0", "id": request_id, "result": value})


def error(request_id: object, code: int, message: str) -> None:
    send({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


def text_result(text: str) -> dict[str, object]:
    return {"content": [{"type": "text", "text": text}]}


def elicitation_fallback(mode: str) -> str:
    return URL_FALLBACK if mode == "url" else FORM_FALLBACK


def handle_elicitation_response(request_id: object, response: dict[str, object]) -> bool:
    if request_id not in PENDING_ELICITATIONS:
        return False
    tool_request_id = PENDING_ELICITATIONS.pop(request_id)
    response_result = response.get("result")
    response_action = response_result.get("action") if isinstance(response_result, dict) else None
    accepted = "error" not in response and response_action == "accept"
    if accepted and tool_request_id["mode"] == "form":
        content = response_result.get("content")
        accepted = (
            isinstance(content, dict)
            and set(content) == {"variant"}
            and isinstance(content.get("variant"), str)
            and content.get("variant") in {"compact", "expanded"}
        )
    if not accepted:
        result(
            tool_request_id["request_id"],
            text_result(elicitation_fallback(tool_request_id["mode"])),
        )
    else:
        result(
            tool_request_id["request_id"],
            text_result(
                f"{tool_request_id['mode']} elicitation response: {json.dumps(response.get('result'))}"
            ),
        )
    return True


def handle(request: object) -> None:
    if not isinstance(request, dict):
        return
    request_id = request.get("id")
    is_response = "method" not in request and ("result" in request or "error" in request)
    if is_response and handle_elicitation_response(request_id, request):
        return
    method, params = request.get("method"), request.get("params", {})
    request_meta = params.get("_meta") if isinstance(params, dict) else None
    if method == "initialize":
        log_initialize(params)
        save_client_capabilities(params)
        result(
            request_id,
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                "serverInfo": {"name": f"spike-echo-{SERVER_NAME}", "version": "0.2.0"},
            },
        )
    elif method == "tools/list":
        result(request_id, {"tools": TOOLS})
    elif method == "resources/list":
        record_event({"method": "resources/list", "meta": request_meta})
        result(
            request_id,
            {
                "resources": [
                    {
                        "uri": VIEWER_URI,
                        "name": "Spike echo viewer",
                        "mimeType": VIEWER_MIME_TYPE,
                        "_meta": VIEWER_RESOURCE_META,
                    }
                ]
            },
        )
    elif method == "resources/read":
        uri = params.get("uri") if isinstance(params, dict) else None
        record_event({"method": "resources/read", "uri": uri, "meta": request_meta})
        if uri == VIEWER_URI:
            result(
                request_id,
                {
                    "contents": [
                        {
                            "uri": VIEWER_URI,
                            "mimeType": VIEWER_MIME_TYPE,
                            "text": VIEWER_HTML,
                            "_meta": VIEWER_RESOURCE_META,
                        }
                    ]
                },
            )
        else:
            error(request_id, -32602, f"unknown resource: {uri}")
    elif method == "prompts/list":
        result(request_id, {"prompts": PROMPTS})
    elif method == "prompts/get":
        name = params.get("name") if isinstance(params, dict) else None
        if name == "spike-prompt":
            arguments = params.get("arguments", {}) if isinstance(params, dict) else {}
            path = arguments.get("path") if isinstance(arguments, dict) else None
            if not isinstance(path, str) or not path:
                error(request_id, -32602, "spike-prompt requires a non-empty path argument")
                return
            result(
                request_id,
                {
                    "description": "Echo preview prompt",
                    "messages": [
                        {
                            "role": "user",
                            "content": {"type": "text", "text": f"Render an echo preview for {path}."},
                        }
                    ],
                },
            )
        else:
            error(request_id, -32602, f"unknown prompt: {name}")
    elif method == "tools/call":
        tool_name = params.get("name") if isinstance(params, dict) else None
        arguments = params.get("arguments", {}) if isinstance(params, dict) else {}
        logged_args: object = arguments
        if tool_name == "viewer_report" and isinstance(arguments, dict):
            logged_args = {
                "hasReport": "report" in arguments,
                "file": arguments.get("file"),
                "touch": arguments.get("touch"),
            }
        record_event(
            {
                "method": "tools/call",
                "name": tool_name,
                "arguments": logged_args,
                "meta": request_meta,
            }
        )
        if tool_name in {"status", "access_status", "render_preview"} and (
            not isinstance(arguments, dict) or arguments
        ):
            error(request_id, -32602, f"{tool_name} does not accept arguments")
            return
        if tool_name == "status":
            result(request_id, text_result(f"status from {SERVER_NAME}"))
        elif tool_name == "access_status":
            result(request_id, text_result("access status: authorized"))
        elif tool_name == "render_preview":
            result(
                request_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": f"render_preview from {SERVER_NAME}; text fallback remains available.",
                        },
                        {"type": "image", "data": PIXEL, "mimeType": "image/png"},
                        {
                            "type": "resource_link",
                            "uri": VIEWER_URI,
                            "name": "Spike echo viewer",
                            "mimeType": VIEWER_MIME_TYPE,
                        },
                    ],
                    "structuredContent": {
                        "server": SERVER_NAME,
                        "surface": "render_preview",
                    },
                },
            )
        elif tool_name == "open_file":
            if not isinstance(arguments, dict) or set(arguments) != {"file"}:
                error(request_id, -32602, "open_file requires exactly one argument: file")
                return
            validated_file = valid_file_input(arguments.get("file"))
            if validated_file is None:
                error(
                    request_id,
                    -32602,
                    "open_file requires file with non-empty string name and resourceUri",
                )
                return
            result(
                request_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"open_file from {SERVER_NAME} for {validated_file['name']} "
                                f"({validated_file['resourceUri']}); text fallback remains available."
                            ),
                        },
                        {
                            "type": "resource_link",
                            "uri": VIEWER_URI,
                            "name": "Spike echo viewer",
                            "mimeType": VIEWER_MIME_TYPE,
                        },
                    ],
                    "structuredContent": {
                        "server": SERVER_NAME,
                        "surface": "open_file",
                        "file": validated_file,
                        "requestMeta": request_meta,
                    },
                },
            )
        elif tool_name == "viewer_report":
            if not isinstance(arguments, dict) or not set(arguments) <= {"report", "file", "touch"}:
                error(
                    request_id,
                    -32602,
                    "viewer_report accepts only optional report, file, and touch arguments",
                )
                return
            report_payload = arguments.get("report")
            if report_payload is not None and not isinstance(report_payload, dict):
                error(request_id, -32602, "viewer_report report must be an object")
                return
            touch = arguments.get("touch", False)
            if not isinstance(touch, bool):
                error(request_id, -32602, "viewer_report touch must be a boolean")
                return
            file_arg = arguments.get("file")
            validated_file = None
            if file_arg is not None:
                validated_file = valid_file_input(file_arg)
                if validated_file is None:
                    error(
                        request_id,
                        -32602,
                        "viewer_report file requires non-empty string name and resourceUri",
                    )
                    return
            host_path = extract_host_path(request_meta)
            touched = maybe_touch_probe_file(host_path, touch)
            reports = SESSION_LOG.get("viewerReports")
            if isinstance(reports, list) and len(reports) < MAX_LOGGED_EVENTS:
                reports.append(
                    {
                        "report": report_payload,
                        "file": validated_file,
                        "requestMeta": request_meta,
                        "touched": touched,
                    }
                )
            flush_log()
            structured = {
                "server": SERVER_NAME,
                "logPath": str(LOG_PATH),
                "requestMeta": request_meta,
                "touched": touched,
                "reportCount": len(reports) if isinstance(reports, list) else 0,
            }
            result(
                request_id,
                {
                    "content": [{"type": "text", "text": json.dumps(structured)}],
                    "structuredContent": structured,
                },
            )
        elif tool_name == "ask":
            if not isinstance(arguments, dict) or set(arguments) != {"mode"}:
                error(request_id, -32602, "ask requires exactly one argument: mode")
                return
            mode = arguments.get("mode") if isinstance(arguments, dict) else None
            if mode not in {"form", "url"}:
                error(request_id, -32602, "ask requires mode form or url")
                return
            if not supports_elicitation(mode):
                result(
                    request_id,
                    text_result(elicitation_fallback(mode)),
                )
                return
            elicitation_id = f"elicitation-{next(ELICITATION_IDS)}"
            PENDING_ELICITATIONS[elicitation_id] = {"request_id": request_id, "mode": mode}
            if mode == "url":
                elicitation_params = {
                    "mode": "url",
                    "elicitationId": elicitation_id,
                    "url": "https://example.invalid/spike-elicitation",
                    "message": "Choose the echo variant.",
                }
            else:
                elicitation_params = {
                    "mode": "form",
                    "message": "Choose the echo variant.",
                    "requestedSchema": {
                        "type": "object",
                        "properties": {"variant": {"type": "string", "enum": ["compact", "expanded"]}},
                        "required": ["variant"],
                        "additionalProperties": False,
                    },
                }
            send(
                {
                    "jsonrpc": "2.0",
                    "id": elicitation_id,
                    "method": "elicitation/create",
                    "params": elicitation_params,
                }
            )
        else:
            error(request_id, -32602, f"unknown tool: {tool_name}")
    elif method == "ui/message":
        return
    elif request_id is not None:
        error(request_id, -32601, f"unknown method: {method}")


def main() -> None:
    for line in sys.stdin:
        try:
            handle(json.loads(line))
        except json.JSONDecodeError:
            error(None, -32700, "parse error")


if __name__ == "__main__":
    main()
