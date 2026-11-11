#!/usr/bin/env python3
"""Prepare self-contained fixture plugins for local harness installation."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ECHO_MCP = ROOT / "echo-mcp"


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").lower() in {"1", "true", "yes"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--auto-probe",
        action="store_true",
        default=env_flag("SPIKE_AUTO_PROBE"),
        help="configure the Antigravity echo MCP servers to run viewer bridge and scratch-file probes automatically on mount",
    )
    parser.add_argument(
        "--auto-probe-message",
        action="store_true",
        default=env_flag("SPIKE_AUTO_PROBE_MESSAGE"),
        help="also send ui/message automatically during --auto-probe",
    )
    options = parser.parse_args()
    auto_probe = options.auto_probe or options.auto_probe_message

    for plugin, server_name in (("p1", "alpha"), ("p2", "beta")):
        plugin_root = ROOT / plugin
        plugin_echo_mcp = plugin_root / "echo-mcp"
        shutil.rmtree(plugin_echo_mcp, ignore_errors=True)
        shutil.copytree(ECHO_MCP, plugin_echo_mcp)

        server = plugin_echo_mcp / "server.py"
        hook_logger = plugin_echo_mcp / "hook-log.sh"
        args = [str(server), server_name]
        server_entry: dict[str, object] = {"command": "python3", "args": args}
        if auto_probe:
            args.append("--auto-probe")
            env_map = {"SPIKE_AUTO_PROBE": "1"}
            if options.auto_probe_message:
                args.append("--auto-probe-message")
                env_map["SPIKE_AUTO_PROBE_MESSAGE"] = "1"
            server_entry["env"] = env_map

        path = plugin_root / "mcp_config.json"
        path.write_text(
            json.dumps(
                {"mcpServers": {server_name: server_entry}},
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        hook_config = {
            plugin: {
                "enabled": True,
                "PostToolUse": [
                    {
                        "matcher": "write_to_file|replace_file_content|multi_replace_file_content",
                        "hooks": [
                            {
                                "type": "command",
                                "command": f"{shlex.quote(str(hook_logger))} post-tool-use",
                            }
                        ],
                    }
                ],
                "Stop": [
                    {"type": "command", "command": f"{shlex.quote(str(hook_logger))} stop"}
                ],
            }
        }
        (ROOT / plugin / "hooks.json").write_text(
            json.dumps(hook_config, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
