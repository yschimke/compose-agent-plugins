#!/usr/bin/env python3
"""Codex app dependencies generated from the canonical plugin source."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate import render_codex_manifest, validate_apps  # noqa: E402


class AppManifestTest(unittest.TestCase):
    def test_validates_supported_fields(self) -> None:
        apps = {
            "compose-preview-catalog": {
                "id": "asdk_app_123",
                "category": "Developer Tools",
                "optional": False,
                "required": True,
            }
        }
        self.assertEqual(apps, validate_apps("compose-catalogs", apps))

    def test_rejects_unknown_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported fields: capabilities"):
            validate_apps(
                "compose-catalogs",
                {"compose-preview-catalog": {"id": "asdk_app_123", "capabilities": []}},
            )

    def test_rejects_non_boolean_requirement_flags(self) -> None:
        for field in ("optional", "required"):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, f"{field} must be a boolean"):
                    validate_apps(
                        "compose-catalogs",
                        {"compose-preview-catalog": {"id": "asdk_app_123", field: "yes"}},
                    )

    def test_rejects_an_unmatched_mcp_alias(self) -> None:
        with self.assertRaisesRegex(ValueError, "aliases must match declared MCP server names"):
            validate_apps(
                "compose-catalogs",
                {"compose_preview": {"id": "asdk_app_123"}},
                [{"name": "compose-preview-catalog"}],
            )

    def test_rejects_an_invalid_registered_app_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "must use an asdk_app_"):
            validate_apps(
                "compose-catalogs",
                {"compose-preview-catalog": {"id": "plugin_asdk_app_123"}},
            )

    def test_codex_manifest_points_at_companion_file(self) -> None:
        manifest = render_codex_manifest(
            name="compose-catalogs",
            version="0.4.0",
            description="Render hosted Compose previews.",
            keywords=["compose"],
            skills=[],
            mcp=[],
            apps={"compose-preview-catalog": {"id": "asdk_app_123"}},
            interface={
                "displayName": "Compose Catalogs",
                "shortDescription": "Render previews.",
                "longDescription": "Render hosted Compose previews.",
                "developerName": "Yuri Schimke",
                "category": "Developer Tools",
                "capabilities": ["Interactive"],
                "defaultPrompt": ["Render a preview."],
            },
            owner="Yuri Schimke",
            repository="https://github.com/yschimke/compose-agent-plugins",
            license_name="Apache-2.0",
        )
        self.assertEqual("./.app.json", manifest["apps"])

    def test_registered_app_is_packaged(self) -> None:
        source = json.loads((ROOT / "src" / "plugins.json").read_text(encoding="utf-8"))
        plugin = next(item for item in source["plugins"] if item["name"] == "compose-catalogs")
        expected = {"apps": validate_apps(plugin["name"], plugin["apps"], plugin["mcp"])}
        generated = json.loads(
            (ROOT / "plugins" / plugin["name"] / ".app.json").read_text(encoding="utf-8")
        )
        self.assertEqual(expected, generated)
        self.assertEqual(
            "asdk_app_6ac4168191c081918c4dfce8370e2842",
            generated["apps"]["compose-preview-catalog"]["id"],
        )
        self.assertIs(generated["apps"]["compose-preview-catalog"]["required"], True)
        manifest = json.loads((ROOT / "plugins" / plugin["name"] / ".codex-plugin/plugin.json").read_text())
        self.assertEqual(plugin["version"], manifest["version"])


if __name__ == "__main__":
    unittest.main()
