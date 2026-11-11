#!/usr/bin/env python3
"""Unit checks for rich-protocol echo fixture responses."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


SERVER_PATH = Path(__file__).resolve().parents[1] / "spike" / "echo-mcp" / "server.py"
SPEC = importlib.util.spec_from_file_location("echo_mcp", SERVER_PATH)
assert SPEC and SPEC.loader
echo_mcp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(echo_mcp)
echo_mcp.SERVER_NAME = "unit"


def call(request: dict) -> dict:
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        echo_mcp.handle(request)
    return json.loads(stdout.getvalue())


def check_viewer_script_syntax(viewer_html: str, scratch: Path) -> None:
    if shutil.which("node") is None:
        return
    start = viewer_html.index("<script>") + len("<script>")
    end = viewer_html.index("</script>", start)
    script_path = scratch / "viewer.js"
    script_path.write_text(viewer_html[start:end], encoding="utf-8")
    completed = subprocess.run(
        ["node", "--check", str(script_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def check_auto_probe_simulation(viewer_html: str, scratch: Path) -> None:
    if shutil.which("node") is None:
        return
    start = viewer_html.index("<script>") + len("<script>")
    end = viewer_html.index("</script>", start)
    script_path = scratch / "viewer-auto.js"
    script_path.write_text(viewer_html[start:end], encoding="utf-8")
    harness_path = scratch / "run-auto-probe-sim.mjs"
    harness_path.write_text(
        """import fs from "node:fs";
import vm from "node:vm";

const code = fs.readFileSync(process.argv[2], "utf8");

function runScenario({uri, name, fileContent}) {
  const elements = new Map();
  const getEl = id => {
    if (!elements.has(id)) {
      elements.set(id, {
        id,
        value: "",
        textContent: "",
        hidden: false,
        listeners: {},
        addEventListener(type, fn) { this.listeners[type] = fn; }
      });
    }
    return elements.get(id);
  };

  let messageListener = null;
  const hostCalls = [];
  const savedReports = [];
  let writtenText = null;

  const parentWindow = {
    postMessage(msg) {
      hostCalls.push(msg);
      if (msg.id === undefined) return;
      setImmediate(() => {
        const respond = payload => messageListener({source: parentWindow, data: {jsonrpc: "2.0", id: msg.id, ...payload}});
        if (msg.method === "ui/initialize") {
          respond({result: {hostInfo: {name: "sim-host", version: "2.31.0"}, hostCapabilities: {openLinks: {}}}});
        } else if (msg.method === "tools/call" && msg.params?.name === "status") {
          respond({result: {content: [{type: "text", text: "status from alpha"}]}});
        } else if (msg.method === "tools/call" && msg.params?.name === "viewer_report") {
          savedReports.push(msg.params.arguments);
          respond({
            result: {
              content: [{type: "text", text: "{}"}],
              structuredContent: {
                server: "alpha",
                logPath: "/tmp/spike-sim.json",
                requestMeta: {"antigravity/resource": {path: "/tmp/sample.uid"}},
                touched: {requested: Boolean(msg.params.arguments?.touch), touched: Boolean(msg.params.arguments?.touch)},
                reportCount: savedReports.length
              }
            }
          });
        } else if (msg.method === "ui/update-model-context") {
          respond({result: {}});
        } else if (msg.method === "resources/read") {
          respond({
            result: {
              contents: [{
                uri: msg.params.uri,
                mimeType: "application/json",
                text: fileContent,
                _meta: {"openai/resource": {writable: true, etag: "etag-1"}}
              }]
            }
          });
        } else if (msg.method === "resources/subscribe") {
          respond({result: {}});
        } else if (msg.method === "openai/resources/write") {
          respond({error: {code: -32601, message: "Method not found"}});
        } else if (msg.method === "resources/write") {
          writtenText = msg.params.text;
          respond({result: {etag: "etag-2"}});
        } else {
          respond({error: {code: -32601, message: `Unhandled ${msg.method}`}});
        }
      });
    }
  };

  const windowObj = {
    parent: parentWindow,
    addEventListener(type, fn) {
      if (type === "message") messageListener = fn;
    }
  };

  const sandbox = {
    window: windowObj,
    document: {getElementById: getEl},
    navigator: {userAgent: "node-sim", clipboard: {writeText: async () => {}}},
    location: {href: "ui://spike/app"},
    setTimeout: fn => setImmediate(fn),
    console
  };

  vm.runInNewContext(code, sandbox);
  setImmediate(() => {
    messageListener({
      source: parentWindow,
      data: {
        jsonrpc: "2.0",
        method: "ui/notifications/tool-input",
        params: {arguments: {file: {name, resourceUri: uri}}}
      }
    });
  });

  return new Promise(resolve => {
    const checkDone = (ticks = 0) => {
      const last = savedReports.at(-1)?.report?.lastTrigger;
      if (last === "auto-file-probe-settled" || last === "auto-file-write-skipped" || ticks > 60) {
        resolve({hostCalls, savedReports, writtenText, reportText: getEl("report").textContent});
      } else {
        setImmediate(() => checkDone(ticks + 1));
      }
    };
    setImmediate(() => checkDone(0));
  });
}

const safeRun = await runScenario({
  uri: "file:///tmp/sample.uid",
  name: "sample.uid",
  fileContent: '{"format": "spike-uid"}\\n'
});
const unsafeRun = await runScenario({
  uri: "file:///Users/dev/project/production.uid",
  name: "production.uid",
  fileContent: '{"screen": "RealUserFile"}\\n'
});
process.stdout.write(JSON.stringify({safeRun, unsafeRun}));
""",
        encoding="utf-8",
    )
    completed = subprocess.run(
        ["node", str(harness_path), str(script_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    outcome = json.loads(completed.stdout)

    safe_final = outcome["safeRun"]["savedReports"][-1]["report"]
    assert safe_final["lastTrigger"] == "auto-file-probe-settled"
    assert safe_final["autoProbe"]["enabled"] is True
    assert safe_final["autoProbe"]["bridgeRan"] is True
    assert safe_final["autoProbe"]["modelContext"] == {"ok": True, "result": {}}
    assert safe_final["autoProbe"]["uiMessage"] is None
    assert safe_final["viewerAction"] == {
        "ok": True,
        "auto": True,
        "statusText": "status from alpha",
    }
    assert safe_final["file"]["read"]["ok"] is True
    assert safe_final["file"]["read"]["etag"] == "etag-1"
    assert safe_final["file"]["subscribe"]["ok"] is True
    assert [attempt["method"] for attempt in safe_final["file"]["writeAttempts"]] == [
        "openai/resources/write",
        "resources/write",
    ]
    assert safe_final["file"]["writeAttempts"][1]["ok"] is True
    assert "_spikeSavedAt" in outcome["safeRun"]["writtenText"]
    assert not any(
        call_msg.get("method") == "ui/message" for call_msg in outcome["safeRun"]["hostCalls"]
    )

    unsafe_final = outcome["unsafeRun"]["savedReports"][-1]["report"]
    assert unsafe_final["lastTrigger"] == "auto-file-write-skipped"
    assert unsafe_final["file"]["read"]["ok"] is True
    assert unsafe_final["file"]["subscribe"]["ok"] is True
    assert unsafe_final["file"]["writeAttempts"] == []
    assert outcome["unsafeRun"]["writtenText"] is None
    assert "refused auto-write" in (unsafe_final["autoProbe"]["writeSkippedReason"] or "")


assert echo_mcp.parse_cli_args([]) == ("unnamed", False, False)
assert echo_mcp.parse_cli_args(["alpha"]) == ("alpha", False, False)
assert echo_mcp.parse_cli_args(["alpha", "--auto-probe"]) == ("alpha", True, False)
assert echo_mcp.parse_cli_args(["--auto-probe-message", "beta"]) == ("beta", True, True)


EXPECTED_TOOLS = {
    "render_preview",
    "open_file",
    "viewer_report",
    "status",
    "access_status",
    "ask",
}

with tempfile.TemporaryDirectory(prefix="echo-mcp-unit-") as temporary_directory:
    scratch = Path(temporary_directory)
    echo_mcp.LOG_PATH = scratch / "spike-unit.json"

    initialize = call(
        {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "echo-unit", "version": "0"},
            },
        }
    )["result"]
    assert initialize["protocolVersion"] == "2025-11-25"
    initial_log = json.loads(echo_mcp.LOG_PATH.read_text(encoding="utf-8"))
    assert initial_log["protocolVersion"] == "2025-11-25"
    assert initial_log["capabilities"] == {}
    assert initial_log["mcpAppsExtension"] is None

    unsupported = call(
        {
            "jsonrpc": "2.0",
            "id": "unsupported",
            "method": "tools/call",
            "params": {"name": "ask", "arguments": {"mode": "form"}},
        }
    )["result"]
    assert unsupported["content"][0]["text"] == echo_mcp.FORM_FALLBACK

    unsupported_url = call(
        {
            "jsonrpc": "2.0",
            "id": "unsupported-url",
            "method": "tools/call",
            "params": {"name": "ask", "arguments": {"mode": "url"}},
        }
    )["result"]
    assert unsupported_url["content"][0]["text"] == echo_mcp.URL_FALLBACK
    assert "https://example.invalid/spike-elicitation" in echo_mcp.URL_FALLBACK
    assert "verification code SPIKE-CODE" in echo_mcp.URL_FALLBACK
    assert "call access_status until it reports authorized" in echo_mcp.URL_FALLBACK
    access_status = call(
        {
            "jsonrpc": "2.0",
            "id": "access-status",
            "method": "tools/call",
            "params": {"name": "access_status", "arguments": {}},
        }
    )["result"]
    assert access_status["content"][0]["text"] == "access status: authorized"

    for zero_argument_tool in ("status", "access_status", "render_preview"):
        rejected_arguments = call(
            {
                "jsonrpc": "2.0",
                "id": f"invalid-{zero_argument_tool}-arguments",
                "method": "tools/call",
                "params": {"name": zero_argument_tool, "arguments": {"unexpected": True}},
            }
        )
        assert rejected_arguments["error"]["code"] == -32602

    invalid_arguments = call(
        {
            "jsonrpc": "2.0",
            "id": "invalid-arguments",
            "method": "tools/call",
            "params": {"name": "ask", "arguments": {"mode": "form", "unexpected": True}},
        }
    )
    assert invalid_arguments["error"]["code"] == -32602

    for bad_open_args in (
        {},
        {"file": {"name": "only-name"}},
        {"file": {"name": "", "resourceUri": "file:///x.uid"}},
        {"file": {"name": "x.uid", "resourceUri": "file:///x.uid", "extra": 1}},
    ):
        rejected_open = call(
            {
                "jsonrpc": "2.0",
                "id": "invalid-open-file",
                "method": "tools/call",
                "params": {"name": "open_file", "arguments": bad_open_args},
            }
        )
        assert rejected_open["error"]["code"] == -32602

    for bad_report_args in (
        {"unexpected": True},
        {"report": "not-an-object"},
        {"touch": "yes"},
        {"file": {"name": ""}},
    ):
        rejected_report = call(
            {
                "jsonrpc": "2.0",
                "id": "invalid-viewer-report",
                "method": "tools/call",
                "params": {"name": "viewer_report", "arguments": bad_report_args},
            }
        )
        assert rejected_report["error"]["code"] == -32602

    mcp_ui_ext = {"mimeTypes": ["text/html;profile=mcp-app"]}
    call(
        {
            "jsonrpc": "2.0",
            "id": "supported",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {
                    "elicitation": {"form": {}, "url": {}},
                    "extensions": {"io.modelcontextprotocol/ui": mcp_ui_ext},
                },
                "clientInfo": {"name": "antigravity-client", "version": "2.31.0"},
            },
        }
    )

    tools = call({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})["result"][
        "tools"
    ]
    assert {tool["name"] for tool in tools} == EXPECTED_TOOLS
    tools_by_name = {tool["name"]: tool for tool in tools}
    assert tools_by_name["render_preview"]["_meta"]["ui"]["resourceUri"] == "ui://spike/app"
    assert tools_by_name["render_preview"]["_meta"]["ui/resourceUri"] == "ui://spike/app"
    assert tools_by_name["open_file"]["_meta"]["openai/ui"]["entrypoints"] == [
        {"type": "file", "extensions": ["uid", "rc"]}
    ]
    assert tools_by_name["viewer_report"]["_meta"]["ui"] == {"visibility": ["app"]}
    assert set(tools_by_name["render_preview"]["outputSchema"]["properties"]) == {
        "server",
        "surface",
    }
    assert set(tools_by_name["open_file"]["outputSchema"]["properties"]) == {
        "server",
        "surface",
        "file",
        "requestMeta",
    }
    assert set(tools_by_name["viewer_report"]["outputSchema"]["properties"]) == {
        "server",
        "logPath",
        "requestMeta",
        "touched",
        "reportCount",
    }

    viewer = call(
        {"jsonrpc": "2.0", "id": 2, "method": "resources/read", "params": {"uri": echo_mcp.VIEWER_URI}}
    )["result"]["contents"][0]
    assert viewer["mimeType"] == "text/html;profile=mcp-app"
    assert viewer["_meta"]["ui"]["prefersBorder"] is True
    assert "postMessage" in viewer["text"]
    for method in (
        "ui/initialize",
        "ui/notifications/initialized",
        "ui/notifications/tool-input",
        "ui/notifications/tool-result",
        "ui/notifications/host-context-changed",
        "notifications/resources/updated",
        "resources/read",
        "resources/subscribe",
        "openai/resources/write",
        "resources/write",
        "tools/call",
        "ui/message",
    ):
        assert method in viewer["text"], method
    assert "event.source !== window.parent" in viewer["text"]
    assert "message.error" in viewer["text"]
    assert "const bridgeReady = initializeBridge();" in viewer["text"]
    assert "await bridgeReady;" in viewer["text"]
    assert 'await request("ui/message", {' in viewer["text"]
    assert 'content: {type: "text", text: "Spike viewer requested status."}' in viewer["text"]
    assert "const AUTO_PROBE = false;" in viewer["text"]
    assert "const AUTO_PROBE_MESSAGE = false;" in viewer["text"]
    check_viewer_script_syntax(viewer["text"], scratch)

    echo_mcp.AUTO_PROBE = True
    try:
        auto_viewer = call(
            {
                "jsonrpc": "2.0",
                "id": "viewer-auto",
                "method": "resources/read",
                "params": {"uri": echo_mcp.VIEWER_URI},
            }
        )["result"]["contents"][0]
    finally:
        echo_mcp.AUTO_PROBE = False
    assert "const AUTO_PROBE = true;" in auto_viewer["text"]
    assert "const AUTO_PROBE_MESSAGE = false;" in auto_viewer["text"]
    check_viewer_script_syntax(auto_viewer["text"], scratch)
    check_viewer_script_syntax(
        echo_mcp.viewer_html(auto_probe=True, auto_probe_message=True), scratch
    )
    check_auto_probe_simulation(auto_viewer["text"], scratch)

    sample_uid = scratch / "sample.uid"
    sample_uid.write_text('{"format": "spike-uid"}\n', encoding="utf-8")
    open_result = call(
        {
            "jsonrpc": "2.0",
            "id": "open-uid",
            "method": "tools/call",
            "params": {
                "name": "open_file",
                "arguments": {
                    "file": {"name": "sample.uid", "resourceUri": sample_uid.as_uri()}
                },
                "_meta": {"antigravity/resource": {"path": str(sample_uid)}},
            },
        }
    )["result"]
    assert "sample.uid" in open_result["content"][0]["text"]
    assert open_result["content"][1]["type"] == "resource_link"
    assert open_result["structuredContent"]["file"]["name"] == "sample.uid"

    disallowed_txt = scratch / "notes.txt"
    disallowed_txt.write_text("plain text\n", encoding="utf-8")
    refused_touch = call(
        {
            "jsonrpc": "2.0",
            "id": "touch-txt",
            "method": "tools/call",
            "params": {
                "name": "viewer_report",
                "arguments": {"touch": True},
                "_meta": {"openai/resource": {"path": str(disallowed_txt)}},
            },
        }
    )["result"]["structuredContent"]
    assert refused_touch["touched"] == {
        "requested": True,
        "touched": False,
        "reason": "unsupported extension",
    }

    accepted_report = call(
        {
            "jsonrpc": "2.0",
            "id": "report-uid",
            "method": "tools/call",
            "params": {
                "name": "viewer_report",
                "arguments": {
                    "report": {
                        "initialize": {"hostCapabilities": {"resources": {"write": True}}},
                        "file": {"writeAttempts": [{"method": "resources/write", "ok": True}]},
                    },
                    "file": {"name": "sample.uid", "resourceUri": sample_uid.as_uri()},
                    "touch": True,
                },
                "_meta": {"antigravity/resource": {"path": str(sample_uid)}},
            },
        }
    )["result"]["structuredContent"]
    assert accepted_report["touched"]["touched"] is True
    assert accepted_report["reportCount"] == 2

    saved_log = json.loads(echo_mcp.LOG_PATH.read_text(encoding="utf-8"))
    assert saved_log["mcpAppsExtension"] == mcp_ui_ext
    assert saved_log["clientInfo"] == {"name": "antigravity-client", "version": "2.31.0"}
    assert any(
        event["method"] == "resources/read" and event["uri"] == echo_mcp.VIEWER_URI
        for event in saved_log["events"]
    )
    assert saved_log["viewerReports"][-1]["report"]["file"]["writeAttempts"] == [
        {"method": "resources/write", "ok": True}
    ]

    missing_prompt_path = call(
        {
            "jsonrpc": "2.0",
            "id": "missing-prompt-path",
            "method": "prompts/get",
            "params": {"name": "spike-prompt", "arguments": {}},
        }
    )
    assert missing_prompt_path["error"]["code"] == -32602

    fallback = call(
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "render_preview", "arguments": {}}}
    )["result"]["content"]
    assert fallback[0]["type"] == "text"
    assert fallback[2]["type"] == "resource_link"

    for request_id, mode in ((4, "form"), (5, "url")):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            echo_mcp.handle(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "tools/call",
                    "params": {"name": "ask", "arguments": {"mode": mode}},
                }
            )
            elicitation = json.loads(stdout.getvalue())
            echo_mcp.handle(
                {
                    "jsonrpc": "2.0",
                    "id": elicitation["id"],
                    "error": {"code": -32601, "message": "unsupported"},
                }
            )
        responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
        assert responses[0]["method"] == "elicitation/create"
        assert responses[0]["params"]["mode"] == mode
        assert responses[1]["id"] == request_id
        assert f"{mode} elicitation unavailable" in responses[1]["result"]["content"][0]["text"]
        if mode == "url":
            assert set(responses[0]["params"]) == {"mode", "elicitationId", "url", "message"}

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        echo_mcp.handle(
            {
                "jsonrpc": "2.0",
                "id": "declined-tool",
                "method": "tools/call",
                "params": {"name": "ask", "arguments": {"mode": "form"}},
            }
        )
        elicitation = json.loads(stdout.getvalue())
        echo_mcp.handle(
            {"jsonrpc": "2.0", "id": elicitation["id"], "result": {"action": "decline"}}
        )
    declined_responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert declined_responses[1]["id"] == "declined-tool"
    assert declined_responses[1]["result"]["content"][0]["text"] == echo_mcp.FORM_FALLBACK

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        echo_mcp.handle(
            {
                "jsonrpc": "2.0",
                "id": "malformed-accept-tool",
                "method": "tools/call",
                "params": {"name": "ask", "arguments": {"mode": "form"}},
            }
        )
        elicitation = json.loads(stdout.getvalue())
        echo_mcp.handle(
            {
                "jsonrpc": "2.0",
                "id": elicitation["id"],
                "result": {"action": "accept", "content": {"variant": []}},
            }
        )
    malformed_accept_responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert malformed_accept_responses[1]["id"] == "malformed-accept-tool"
    assert malformed_accept_responses[1]["result"]["content"][0]["text"] == echo_mcp.FORM_FALLBACK


    def start_elicitation(tool_request_id: str) -> dict:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            echo_mcp.handle(
                {
                    "jsonrpc": "2.0",
                    "id": tool_request_id,
                    "method": "tools/call",
                    "params": {"name": "ask", "arguments": {"mode": "form"}},
                }
            )
        return json.loads(stdout.getvalue())


    first = start_elicitation("first-tool")
    second = start_elicitation("second-tool")
    call(
        {
            "jsonrpc": "2.0",
            "id": first["id"],
            "result": {"action": "accept", "content": {"variant": "compact"}},
        }
    )
    third = start_elicitation("third-tool")
    assert len({first["id"], second["id"], third["id"]}) == 3
    for elicitation in (second, third):
        call({"jsonrpc": "2.0", "id": elicitation["id"], "result": {"action": "cancel"}})

    overlap = start_elicitation("overlap-tool")
    overlapping_request = call(
        {"jsonrpc": "2.0", "id": overlap["id"], "method": "tools/list", "params": {}}
    )
    assert {tool["name"] for tool in overlapping_request["result"]["tools"]} == EXPECTED_TOOLS
    assert overlap["id"] in echo_mcp.PENDING_ELICITATIONS
    call({"jsonrpc": "2.0", "id": overlap["id"], "result": {"action": "cancel"}})

print("echo MCP unit tests passed")
