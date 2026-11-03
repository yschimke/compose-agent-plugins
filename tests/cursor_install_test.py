#!/usr/bin/env python3
"""Tests for scripts/cursor-install.py: local copy, sibling removal, catalogs, review."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "cursor-install.py"
CHECK = ROOT / "scripts" / "cursor-check.py"
SMOKE = ROOT / "scripts" / "cursor-smoke.py"


class CursorInstallTest(unittest.TestCase):
    def run_install(self, plugins_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--plugins-dir", str(plugins_dir), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_installs_compose_preview_from_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugins_dir = Path(directory)
            result = self.run_install(plugins_dir)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            installed = plugins_dir / "compose-preview"
            manifest = json.loads(
                (installed / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8")
            )
            self.assertEqual("compose-preview", manifest["name"])
            self.assertIn("compose-preview-mcp", manifest["mcpServers"])
            self.assertIn("compose-preview-catalog", manifest["mcpServers"])
            self.assertEqual("./assets/compose-preview-logo.png", manifest.get("logo"))
            self.assertTrue(
                (installed / "assets" / "compose-preview-logo.png").is_file()
            )
            self.assertTrue((installed / "skills" / "compose-preview" / "SKILL.md").is_file())
            self.assertTrue((installed / "agents" / "design-reviewer.md").is_file())
            self.assertFalse((installed / ".claude-plugin").exists())
            self.assertFalse((installed / ".codex-plugin").exists())
            self.assertTrue((installed / "hooks" / "hooks.json").is_file())
            self.assertEqual({"version": 1, "hooks": {}}, manifest["hooks"])

    def test_catalogs_replaces_preview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugins_dir = Path(directory)
            first = self.run_install(plugins_dir)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            second = self.run_install(plugins_dir, "--catalogs")
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertFalse((plugins_dir / "compose-preview").exists())
            catalogs = plugins_dir / "compose-catalogs"
            manifest = json.loads(
                (catalogs / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8")
            )
            self.assertEqual("compose-catalogs", manifest["name"])
            self.assertEqual(["compose-preview-catalog"], sorted(manifest["mcpServers"]))
            self.assertNotIn("compose-preview-mcp", manifest["mcpServers"])
            self.assertEqual("./assets/compose-preview-logo.png", manifest.get("logo"))

    def test_review_installs_alongside_preview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugins_dir = Path(directory)
            result = self.run_install(plugins_dir, "--review")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((plugins_dir / "compose-preview").is_dir())
            review = plugins_dir / "compose-review"
            manifest = json.loads(
                (review / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8")
            )
            self.assertEqual("compose-review", manifest["name"])
            self.assertTrue(
                (review / "skills" / "compose-preview-review" / "SKILL.md").is_file()
            )
            self.assertTrue(
                (review / "skills" / "compose-preview-ci" / "SKILL.md").is_file()
            )

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugins_dir = Path(directory)
            result = self.run_install(plugins_dir, "--dry-run")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual([], list(plugins_dir.iterdir()))
            self.assertIn("would copy", result.stdout)

    def test_check_passes_after_install(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugins_dir = Path(directory)
            install = self.run_install(plugins_dir)
            self.assertEqual(install.returncode, 0, install.stdout + install.stderr)
            check = subprocess.run(
                [sys.executable, str(CHECK), "--plugins-dir", str(plugins_dir)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
            self.assertIn("empty inline hooks", check.stdout)
            self.assertIn("design-reviewer", check.stdout)
            self.assertIn("marketplace logo", check.stdout)

    def test_smoke_check_only(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SMOKE), "--check-only", "--skip-schema"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("design-reviewer", result.stdout)
        self.assertIn("marketplace logo", result.stdout)
        self.assertIn("submit fields ok", result.stdout)
        self.assertIn("Static checks passed", result.stdout)


if __name__ == "__main__":
    unittest.main()