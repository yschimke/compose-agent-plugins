#!/usr/bin/env python3
"""Tests for scripts/opencode-install.py: config merging and bundle installation."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("opencode_install", ROOT / "scripts" / "opencode-install.py")
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)
BUNDLE = json.loads((ROOT / "opencode" / "opencode.json").read_text(encoding="utf-8"))
PNG_RULE = "*/compose-preview-mcp-*"


class MergeConfigTest(unittest.TestCase):
    def test_empty_config_gets_both_servers_and_png_rule(self) -> None:
        config: dict = {}
        changes = installer.merge_config(config, BUNDLE)
        self.assertEqual(set(config["mcp"]["servers"]), {"compose-preview-mcp", "compose-preview-catalog"})
        self.assertEqual(config["permission"]["external_directory"], {PNG_RULE: "allow"})
        self.assertEqual(len(changes), 3)
        self.assertEqual(installer.merge_config(config, BUNDLE), [], "a second merge changes nothing")

    def test_keeps_an_existing_v2_entry_and_other_keys(self) -> None:
        mine = {"type": "local", "command": ["compose-preview", "mcp", "serve", "--project=/app"]}
        config = {"mcp": {"servers": {"compose-preview-mcp": mine}}, "permission": {"bash": "ask"}}
        installer.merge_config(config, BUNDLE)
        self.assertIs(config["mcp"]["servers"]["compose-preview-mcp"], mine)
        self.assertEqual(config["permission"]["bash"], "ask")
        self.assertIn("compose-preview-catalog", config["mcp"]["servers"])

    def test_v1_shape_gets_v1_entries(self) -> None:
        mine = {"type": "local", "command": ["compose-preview", "mcp", "serve"]}
        config = {"mcp": {"compose-preview-mcp": mine}}
        installer.merge_config(config, BUNDLE)
        self.assertNotIn("servers", config["mcp"])
        self.assertIs(config["mcp"]["compose-preview-mcp"], mine)
        self.assertNotIn("codemode", config["mcp"]["compose-preview-catalog"])

    def test_scalar_permissions_keep_their_default_and_gain_the_png_rule(self) -> None:
        cases = (
            ({"external_directory": "ask"}, {"external_directory": {"*": "ask", PNG_RULE: "allow"}}),
            ({"bash": "ask", "external_directory": "deny"},
             {"bash": "ask", "external_directory": {"*": "deny", PNG_RULE: "allow"}}),
            ("ask", {"*": "ask", "external_directory": {"*": "ask", PNG_RULE: "allow"}}),
            ({"*": "deny"}, {"*": "deny", "external_directory": {"*": "deny", PNG_RULE: "allow"}}),
        )
        for permission, expected in cases:
            with self.subTest(permission=permission):
                config = {"permission": json.loads(json.dumps(permission))}
                changes = installer.merge_config(config, BUNDLE)
                self.assertEqual(config["permission"], expected)
                self.assertIn(f"allowed reading rendered PNGs ({PNG_RULE})", changes)

    def test_leaves_blanket_permissions_alone(self) -> None:
        for permission in ("allow", {"external_directory": "allow"}):
            config = {"permission": json.loads(json.dumps(permission))}
            installer.merge_config(config, BUNDLE)
            self.assertEqual(config["permission"], permission)


class InstallTest(unittest.TestCase):
    def run_install(self, config_dir: Path, dry_run: bool = False) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = installer.install(config_dir, installer.read_bundle("main"), dry_run)
        return status, output.getvalue()

    def test_installs_bundle_files_and_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_dir = Path(directory)
            status, _ = self.run_install(config_dir)
            self.assertEqual(status, 0)
            for name in ("agents/design-reviewer.md", "plugins/compose-preview.js", "skills/harness-notes/SKILL.md"):
                self.assertEqual((config_dir / name).read_bytes(), (ROOT / "opencode" / name).read_bytes())
            config = json.loads((config_dir / "opencode.json").read_text(encoding="utf-8"))
            self.assertIn("compose-preview-catalog", config["mcp"]["servers"])
            status, output = self.run_install(config_dir)
            self.assertEqual(status, 0)
            self.assertNotIn("write", output)
            self.assertIn("already has both servers", output)

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            status, output = self.run_install(Path(directory), dry_run=True)
            self.assertEqual(status, 0)
            self.assertIn("would write", output)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_jsonc_is_never_rewritten(self) -> None:
        for name, text in (("opencode.jsonc", '{"theme": "dark"}\n'), ("opencode.json", '// mine\n{}\n')):
            with tempfile.TemporaryDirectory() as directory, self.subTest(name=name):
                path = Path(directory) / name
                path.write_text(text, encoding="utf-8")
                status, output = self.run_install(Path(directory))
                self.assertEqual(status, 1)
                self.assertEqual(path.read_text(encoding="utf-8"), text)
                self.assertIn('"compose-preview-catalog"', output)


if __name__ == "__main__":
    unittest.main()
