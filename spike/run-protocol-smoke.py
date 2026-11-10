#!/usr/bin/env python3
"""Exercise the fixture directly; this is a protocol baseline, not a harness result."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def request(
    process: subprocess.Popen[str],
    request_id: int,
    method: str,
    params: dict,
) -> dict:
    assert process.stdin and process.stdout
    process.stdin.write(
        json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}) + "\n"
    )
    process.stdin.flush()
    response = json.loads(process.stdout.readline())
    assert response["id"] == request_id, response
    return response["result"]


def run(plugin: str, server_name: str, scratch: Path) -> None:
    server = ROOT / plugin / "echo-mcp" / "server.py"
    log_path = scratch / f"spike-{server_name}.json"
    probe_uid = scratch / f"{server_name}-sample.uid"
    probe_uid.write_text('{"format": "spike-uid"}\n', encoding="utf-8")
    env = {
        **os.environ,
        "SPIKE_LOG_PATH": str(log_path),
        "ANTIGRAVITY_CLI_ALIAS": "agy",
    }
    process = subprocess.Popen(
        [sys.executable, str(server), server_name],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        mcp_apps_cap = {"mimeTypes": ["text/html;profile=mcp-app"]}
        initialize = request(
            process,
            1,
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {
                    "elicitation": {"form": {}, "url": {}},
                    "extensions": {"io.modelcontextprotocol/ui": mcp_apps_cap},
                },
                "clientInfo": {"name": "spike-smoke", "version": "0"},
            },
        )
        assert initialize["serverInfo"]["name"] == f"spike-echo-{server_name}"
        assert initialize["protocolVersion"] == "2025-11-25"
        assert {"tools", "resources", "prompts"} <= set(initialize["capabilities"])

        tools = request(process, 2, "tools/list", {})["tools"]
        tools_by_name = {tool["name"]: tool for tool in tools}
        assert set(tools_by_name) == {
            "render_preview",
            "open_file",
            "viewer_report",
            "status",
            "access_status",
            "ask",
        }
        assert tools_by_name["render_preview"]["_meta"]["ui"]["resourceUri"] == "ui://spike/app"
        assert tools_by_name["render_preview"]["_meta"]["ui/resourceUri"] == "ui://spike/app"
        assert tools_by_name["open_file"]["_meta"]["ui"]["resourceUri"] == "ui://spike/app"
        assert tools_by_name["open_file"]["_meta"]["openai/ui"]["entrypoints"] == [
            {"type": "file", "extensions": ["uid", "rc"]}
        ]
        assert tools_by_name["viewer_report"]["_meta"]["ui"]["visibility"] == ["app"]
        for structured_tool, required_keys in (
            ("render_preview", {"server", "surface"}),
            ("open_file", {"server", "surface", "file", "requestMeta"}),
            ("viewer_report", {"server", "logPath", "requestMeta", "touched", "reportCount"}),
        ):
            output_schema = tools_by_name[structured_tool]["outputSchema"]
            assert output_schema["type"] == "object"
            assert set(output_schema["required"]) == required_keys

        status = request(process, 3, "tools/call", {"name": "status", "arguments": {}})
        assert status["content"][0]["text"] == f"status from {server_name}"

        preview = request(process, 4, "tools/call", {"name": "render_preview", "arguments": {}})
        assert preview["content"][0]["type"] == "text"
        assert preview["content"][1]["type"] == "image"
        assert preview["content"][2]["type"] == "resource_link"
        assert preview["structuredContent"] == {
            "server": server_name,
            "surface": "render_preview",
        }

        opened = request(
            process,
            5,
            "tools/call",
            {
                "name": "open_file",
                "arguments": {
                    "file": {
                        "name": probe_uid.name,
                        "resourceUri": probe_uid.as_uri(),
                    }
                },
                "_meta": {"openai/resource": {"path": str(probe_uid)}},
            },
        )
        assert probe_uid.name in opened["content"][0]["text"]
        assert opened["content"][1]["type"] == "resource_link"
        assert opened["structuredContent"]["file"]["resourceUri"] == probe_uid.as_uri()
        assert opened["structuredContent"]["requestMeta"] == {
            "openai/resource": {"path": str(probe_uid)}
        }

        reported = request(
            process,
            6,
            "tools/call",
            {
                "name": "viewer_report",
                "arguments": {
                    "report": {"initialize": {"hostInfo": {"name": "smoke-host"}}},
                    "file": {"name": probe_uid.name, "resourceUri": probe_uid.as_uri()},
                    "touch": True,
                },
                "_meta": {"openai/resource": {"path": str(probe_uid)}},
            },
        )
        assert reported["structuredContent"]["touched"]["touched"] is True
        assert reported["structuredContent"]["reportCount"] == 1

        resources = request(process, 7, "resources/list", {})["resources"]
        assert len(resources) == 1
        assert resources[0]["uri"] == "ui://spike/app"
        assert resources[0]["name"] == "Spike echo viewer"
        assert resources[0]["mimeType"] == "text/html;profile=mcp-app"
        assert resources[0]["_meta"]["ui"]["prefersBorder"] is True

        viewer = request(process, 8, "resources/read", {"uri": "ui://spike/app"})["contents"][0]
        assert viewer["mimeType"] == "text/html;profile=mcp-app"
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
        assert "event.source !== window.parent" in viewer["text"] and "message.error" in viewer["text"]
        assert "const bridgeReady = initializeBridge();" in viewer["text"]
        assert "await bridgeReady;" in viewer["text"]
        assert 'await request("ui/message", {' in viewer["text"]
        assert 'content: {type: "text", text: "Spike viewer requested status."}' in viewer["text"]

        prompt = request(
            process, 9, "prompts/get", {"name": "spike-prompt", "arguments": {"path": "Example.kt"}}
        )
        assert prompt["messages"][0]["content"]["text"] == "Render an echo preview for Example.kt."
        assert request(process, 10, "prompts/list", {})["prompts"][0]["name"] == "spike-prompt"

        logged = json.loads(log_path.read_text(encoding="utf-8"))
        assert logged["serverName"] == server_name
        assert logged["protocolVersion"] == "2025-11-25"
        assert logged["mcpAppsExtension"] == mcp_apps_cap
        assert logged["detectionEnvironment"]["ANTIGRAVITY_CLI_ALIAS"] == "agy"
        assert [entry["method"] for entry in logged["events"]][:3] == [
            "initialize",
            "tools/call",
            "tools/call",
        ]
        assert any(
            entry["method"] == "resources/read" and entry["uri"] == "ui://spike/app"
            for entry in logged["events"]
        )
        assert len(logged["viewerReports"]) == 1
        assert logged["viewerReports"][0]["report"]["initialize"]["hostInfo"]["name"] == "smoke-host"

        assert process.stdin and process.stdout
        for request_id, mode in ((11, "form"), (12, "url")):
            process.stdin.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "method": "tools/call",
                        "params": {"name": "ask", "arguments": {"mode": mode}},
                    }
                )
                + "\n"
            )
            process.stdin.flush()
            elicitation = json.loads(process.stdout.readline())
            assert elicitation["method"] == "elicitation/create"
            assert elicitation["params"]["mode"] == mode
            if mode == "form":
                assert elicitation["params"]["requestedSchema"]["properties"]["variant"]["enum"] == [
                    "compact",
                    "expanded",
                ]
            else:
                assert set(elicitation["params"]) == {"mode", "elicitationId", "url", "message"}
            process.stdin.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": elicitation["id"],
                        "result": {"action": "accept", "content": {"variant": "compact"}},
                    }
                )
                + "\n"
            )
            process.stdin.flush()
            elicitation_result = json.loads(process.stdout.readline())
            assert elicitation_result["id"] == request_id
            assert mode in elicitation_result["result"]["content"][0]["text"]
    finally:
        process.terminate()
        process.wait(timeout=5)


def run_fallback(plugin: str, server_name: str, scratch: Path) -> None:
    server = ROOT / plugin / "echo-mcp" / "server.py"
    env = {
        **os.environ,
        "SPIKE_LOG_PATH": str(scratch / f"spike-fallback-{server_name}.json"),
    }
    process = subprocess.Popen(
        [sys.executable, str(server), server_name],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        request(
            process,
            1,
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "spike-fallback-smoke", "version": "0"},
            },
        )
        form = request(
            process,
            2,
            "tools/call",
            {"name": "ask", "arguments": {"mode": "form"}},
        )["content"][0]["text"]
        assert "compact or expanded" in form
        url = request(
            process,
            3,
            "tools/call",
            {"name": "ask", "arguments": {"mode": "url"}},
        )["content"][0]["text"]
        assert "https://example.invalid/spike-elicitation" in url
        assert "verification code SPIKE-CODE" in url
        assert "call access_status until it reports authorized" in url
        access_status = request(
            process,
            4,
            "tools/call",
            {"name": "access_status", "arguments": {}},
        )["content"][0]["text"]
        assert access_status == "access status: authorized"
    finally:
        process.terminate()
        process.wait(timeout=5)


with tempfile.TemporaryDirectory(prefix="spike-protocol-smoke-") as directory:
    scratch_dir = Path(directory)
    for plugin, name in (("p1", "alpha"), ("p2", "beta")):
        run(plugin, name, scratch_dir)
        run_fallback(plugin, name, scratch_dir)
print("spike MCP protocol smoke test passed for alpha and beta")
