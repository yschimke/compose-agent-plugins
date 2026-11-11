#!/usr/bin/env python3
"""Tests for scripts/antigravity-mcp-apps-smoke.py (--check-only and --logs-dir)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "scripts" / "antigravity-mcp-apps-smoke.py"


class AntigravityMcpAppsSmokeTest(unittest.TestCase):
    def test_check_only_prepares_and_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SMOKE), "--check-only"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("prepared spike/p1 and spike/p2", result.stdout)
        self.assertIn("protocol baseline passed", result.stdout)
        self.assertIn("Static and protocol checks passed.", result.stdout)

    def test_auto_probe_check_only_wires_flag_and_restores_default(self) -> None:
        auto_result = subprocess.run(
            [sys.executable, str(SMOKE), "--auto-probe", "--check-only"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(auto_result.returncode, 0, auto_result.stdout + auto_result.stderr)
        self.assertIn("(with --auto-probe)", auto_result.stdout)
        p1_mcp = json.loads((ROOT / "spike" / "p1" / "mcp_config.json").read_text(encoding="utf-8"))
        alpha_entry = p1_mcp["mcpServers"]["alpha"]
        self.assertIn("--auto-probe", alpha_entry["args"])
        self.assertEqual(alpha_entry.get("env"), {"SPIKE_AUTO_PROBE": "1"})

        default_result = subprocess.run(
            [sys.executable, str(SMOKE), "--check-only"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(default_result.returncode, 0, default_result.stdout + default_result.stderr)
        restored_mcp = json.loads(
            (ROOT / "spike" / "p1" / "mcp_config.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("--auto-probe", restored_mcp["mcpServers"]["alpha"]["args"])
        self.assertNotIn("env", restored_mcp["mcpServers"]["alpha"])

    def test_logs_dir_summarizes_capabilities_and_viewer_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            logs_dir = Path(directory)
            sample_log = logs_dir / "spike-12345.json"
            sample_log.write_text(
                json.dumps(
                    {
                        "serverName": "alpha",
                        "autoProbe": True,
                        "protocolVersion": "2025-11-25",
                        "clientInfo": {"name": "antigravity", "version": "2.31.0"},
                        "capabilities": {
                            "extensions": {
                                "io.modelcontextprotocol/ui": {
                                    "mimeTypes": ["text/html;profile=mcp-app"]
                                }
                            }
                        },
                        "mcpAppsExtension": {
                            "mimeTypes": ["text/html;profile=mcp-app"]
                        },
                        "detectionEnvironment": {"ANTIGRAVITY_CLI_ALIAS": "agy"},
                        "events": [
                            {"method": "initialize"},
                            {"method": "resources/read", "uri": "ui://spike/app"},
                            {"method": "tools/call", "name": "open_file"},
                        ],
                        "viewerReports": [
                            {
                                "requestMeta": {
                                    "antigravity/resource": {"path": "/tmp/sample.uid"}
                                },
                                "report": {
                                    "lastTrigger": "auto-file-probe-settled",
                                    "autoProbe": {
                                        "enabled": True,
                                        "bridgeRan": True,
                                        "fileUrisProbed": ["file:///tmp/sample.uid"],
                                    },
                                    "viewerAction": {
                                        "ok": True,
                                        "auto": True,
                                        "statusText": "status from alpha",
                                    },
                                    "initialize": {
                                        "hostInfo": {"name": "antigravity", "version": "2.31.0"},
                                        "hostCapabilities": {"openLinks": {}},
                                    },
                                    "toolResult": {
                                        "contentTypes": ["text", "resource_link"],
                                        "structuredContent": {"surface": "open_file"},
                                    },
                                    "file": {
                                        "read": {"ok": True, "representation": "text"},
                                        "writeAttempts": [
                                            {"method": "openai/resources/write", "ok": True}
                                        ],
                                    },
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(SMOKE), "--logs-dir", str(logs_dir)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("autoProbe=True", result.stdout)
            self.assertIn("'antigravity'@'2.31.0'", result.stdout)
            self.assertIn("text/html;profile=mcp-app", result.stdout)
            self.assertIn("ui://spike/app", result.stdout)
            self.assertIn("status from alpha", result.stdout)
            self.assertIn("autoProbe state:", result.stdout)
            self.assertIn("openai/resources/write", result.stdout)
            self.assertIn("/tmp/sample.uid", result.stdout)


if __name__ == "__main__":
    unittest.main()
