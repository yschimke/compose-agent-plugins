#!/usr/bin/env python3
"""The OpenAI onboarding skill (extensions["com.openai"].onboardingSkill) in the Codex manifest."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate import codex_skill_config, render_codex_manifest  # noqa: E402


def manifest(**overrides: object) -> dict[str, object]:
    inputs: dict[str, object] = {
        "name": "compose-preview",
        "version": "0.2.0",
        "description": "Render previews.",
        "keywords": ["compose"],
        "skills": ["harness-notes", "compose-preview-setup"],
        "mcp": [],
        "apps": {},
        "interface": {
            "displayName": "Compose Preview",
            "shortDescription": "Render previews.",
            "longDescription": "Render Compose previews.",
            "developerName": "Yuri Schimke",
            "category": "Developer Tools",
            "capabilities": ["Interactive"],
            "defaultPrompt": ["Render a preview."],
        },
        "owner": "Yuri Schimke",
        "repository": "https://github.com/yschimke/compose-agent-plugins",
        "license_name": "Apache-2.0",
    }
    inputs.update(overrides)
    return render_codex_manifest(**inputs)  # type: ignore[arg-type]


class OnboardingSkillTest(unittest.TestCase):
    def test_absent_by_default(self) -> None:
        self.assertNotIn("extensions", manifest())

    def test_points_at_the_packaged_skill(self) -> None:
        self.assertEqual(
            {"com.openai": {"onboardingSkill": "./skills/compose-preview-setup/SKILL.md"}},
            manifest(onboarding_skill="compose-preview-setup")["extensions"],
        )

    def test_subset_onboarding_uses_the_codex_skill_directory(self) -> None:
        actual = manifest(skills_path="./.codex-plugin/skills/",
                          onboarding_skill="compose-preview-setup")
        self.assertEqual("./.codex-plugin/skills/", actual["skills"])
        self.assertEqual("./.codex-plugin/skills/compose-preview-setup/SKILL.md",
                         actual["extensions"]["com.openai"]["onboardingSkill"])

    def test_codex_subset_rejects_unknown_and_duplicate_skills(self) -> None:
        for selected in (["unknown"], ["harness-notes", "harness-notes"], "harness-notes"):
            with self.subTest(selected=selected), self.assertRaisesRegex(ValueError, "unique subset"):
                codex_skill_config({"name": "example", "skills": ["harness-notes"],
                                    "codexSkills": selected})

    def test_codex_excludes_antigravity_card_but_other_hosts_keep_it(self) -> None:
        root = ROOT / "plugins" / "compose-preview"
        codex = json.loads((root / ".codex-plugin" / "plugin.json").read_text())
        self.assertFalse((root / codex["skills"] / "antigravity-viewer-card").exists())
        self.assertTrue((root / "skills" / "antigravity-viewer-card" / "SKILL.md").is_file())

    def test_rejects_a_skill_the_plugin_does_not_package(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be one of the plugin's skills"):
            manifest(onboarding_skill="setup")

    def test_rejects_a_blank_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "onboardingSkill must be a non-empty string"):
            manifest(onboarding_skill=" ")

    def test_every_shipped_plugin_onboards_with_a_packaged_skill(self) -> None:
        source = json.loads((ROOT / "src" / "plugins.json").read_text(encoding="utf-8"))
        for plugin in source["plugins"]:
            name = plugin["name"]
            codex = json.loads(
                (ROOT / "plugins" / name / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
            )
            path = codex["extensions"]["com.openai"]["onboardingSkill"]
            self.assertTrue((ROOT / "plugins" / name / path).is_file(), f"{name}: {path}")
            for other in ("plugin.json", ".claude-plugin/plugin.json", ".cursor-plugin/plugin.json"):
                other_manifest = json.loads((ROOT / "plugins" / name / other).read_text(encoding="utf-8"))
                self.assertNotIn("extensions", other_manifest, f"{name}/{other}")


if __name__ == "__main__":
    unittest.main()
