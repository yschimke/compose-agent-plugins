#!/usr/bin/env python3
"""Regression checks for the cached-plugin spike fixture."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SPIKE_ROOT = REPOSITORY_ROOT / "spike"


def hook_commands(hooks: dict) -> list[str]:
    commands: list[str] = []
    for event in hooks["hooks"].values():
        for entry in event:
            for hook in entry["hooks"]:
                commands.append(hook["command"])
    return commands


def assert_session_start_hook(hooks: dict) -> None:
    session_start = hooks["hooks"]["SessionStart"]
    assert len(session_start) == 1
    command = session_start[0]["hooks"][0]["command"]
    assert command == '"${CLAUDE_PLUGIN_ROOT}/echo-mcp/hook-log.sh" session-start'


def assert_cached_plugin(plugin_name: str, server_name: str, cache_root: Path) -> None:
    plugin = cache_root / plugin_name
    cached_plugin = cache_root / "cached" / plugin_name
    shutil.copytree(plugin, cached_plugin)

    server = cached_plugin / "echo-mcp" / "server.py"
    logger = cached_plugin / "echo-mcp" / "hook-log.sh"
    assert server.is_file(), server
    assert logger.is_file(), logger
    if plugin_name == "p1":
        reviewer = cached_plugin / "agents" / "spike-reviewer.md"
        assert reviewer.is_file(), reviewer
        assert "SPIKE-REVIEWER-LOADED" in reviewer.read_text(encoding="utf-8")

    codex = json.loads(
        (cached_plugin / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert codex["name"] == plugin_name
    assert codex["skills"] == "./skills/"
    assert codex["mcpServers"] == "./.codex-mcp.json"

    # Codex resolves package-relative args through cwd; its expansion of
    # ${CLAUDE_PLUGIN_ROOT} in args is unconfirmed, so it keeps its own file.
    codex_mcp = json.loads((cached_plugin / ".codex-mcp.json").read_text(encoding="utf-8"))
    codex_configured = codex_mcp["mcpServers"][server_name]
    assert codex_configured["cwd"] == "."
    assert cached_plugin / codex_configured["args"][0] == server

    # Claude Code resolves relative args against the session directory and ignores cwd.
    mcp = json.loads((cached_plugin / ".mcp.json").read_text(encoding="utf-8"))
    configured = mcp["mcpServers"][server_name]
    assert "cwd" not in configured
    assert configured["args"][0] == "${CLAUDE_PLUGIN_ROOT}/echo-mcp/server.py"
    configured_server = Path(configured["args"][0].replace("${CLAUDE_PLUGIN_ROOT}", str(cached_plugin)))
    assert configured_server == server
    assert configured_server.is_file(), configured_server

    hooks = json.loads((cached_plugin / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    assert_session_start_hook(hooks)
    for command in hook_commands(hooks):
        assert command.startswith('"${CLAUDE_PLUGIN_ROOT}/'), command
        executable = Path(command[1 : command.index('"', 1)].replace("${CLAUDE_PLUGIN_ROOT}", str(cached_plugin)))
        assert executable == logger
        assert executable.is_file(), executable
        assert "/../" not in command

    request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n"
    server_env = {**os.environ, "SPIKE_LOG_PATH": str(cache_root / f"{plugin_name}-mcp.json")}
    result = subprocess.run(
        [sys.executable, str(configured_server), server_name],
        input=request,
        text=True,
        capture_output=True,
        env=server_env,
        check=True,
    )
    response = json.loads(result.stdout)
    assert response["result"]["serverInfo"]["name"] == f"spike-echo-{server_name}"

    payload = "x" * (200 * 1024)
    log_path = cache_root / f"{plugin_name}-hooks.log"
    environment = {**os.environ, "SPIKE_HOOK_LOG_PATH": str(log_path)}
    subprocess.run([str(logger), "post-tool-use"], input=payload, text=True, env=environment, check=True)
    record = json.loads(log_path.read_text(encoding="utf-8"))
    assert record["event"] == "post-tool-use"
    assert record["stdin"] == payload
    session_start_result = subprocess.run(
        [str(logger), "session-start"], input="", text=True, env=environment, capture_output=True, check=True
    )
    assert session_start_result.stdout == "SPIKE-SESSION-START\n"
    session_start = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
    assert session_start["probe"] == "SPIKE-SESSION-START"


def main() -> None:
    stale_file = SPIKE_ROOT / "p1" / "echo-mcp" / "stale-helper"
    stale_file.parent.mkdir(parents=True, exist_ok=True)
    stale_file.write_text("stale", encoding="utf-8")
    subprocess.run([sys.executable, str(SPIKE_ROOT / "prepare.py")], check=True)
    assert not stale_file.exists(), stale_file
    with tempfile.TemporaryDirectory() as temporary_directory:
        cache_root = Path(temporary_directory)
        for plugin_name, server_name in (("p1", "alpha"), ("p2", "beta")):
            shutil.copytree(SPIKE_ROOT / plugin_name, cache_root / plugin_name)
            assert_cached_plugin(plugin_name, server_name, cache_root)
    print("spike fixture cache tests passed")


if __name__ == "__main__":
    main()
