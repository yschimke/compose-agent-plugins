#!/usr/bin/env python3
"""scripts/update-skills.py vendors whole skill directories, and hand edits to them are caught."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, check=check, text=True, capture_output=True)


def git(cwd: Path, *args: str) -> str:
    return run("git", *args, cwd=cwd).stdout.strip()


def init_repository(path: Path) -> None:
    git(path, "init", "--quiet")
    git(path, "config", "user.email", "test@example.invalid")
    git(path, "config", "user.name", "Skills test")
    git(path, "config", "core.hooksPath", "/dev/null")


class UpdateSkillsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        temporary = Path(self.directory.name)
        self.fixture = temporary / "repository"
        shutil.copytree(ROOT, self.fixture, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        self.upstream = temporary / "skills"
        self.skills = json.loads((self.fixture / "src/vendor/skills/provenance.json").read_text())["skills"]
        for skill in self.skills:
            skill_root = self.upstream / "skills" / skill
            (skill_root / "references").mkdir(parents=True)
            (skill_root / "SKILL.md").write_text(
                f"---\nname: {skill}\ndescription: Fixture {skill} skill.\n---\n\n# {skill}\n"
            )
            (skill_root / "references" / "more.md").write_text("# More\n")
            script = skill_root / "scripts" / "tool"
            script.parent.mkdir()
            script.write_text("#!/bin/sh\necho tool\n")
            script.chmod(0o755)
        (self.upstream / "skills" / "unvendored").mkdir()
        (self.upstream / "skills" / "unvendored" / "SKILL.md").write_text("---\nname: unvendored\n---\n")
        init_repository(self.upstream)
        git(self.upstream, "add", ".")
        git(self.upstream, "commit", "--quiet", "-m", "fixture skills")
        self.commit = git(self.upstream, "rev-parse", "HEAD")

    def update(self) -> None:
        run(sys.executable, "scripts/update-skills.py", "--from-local", str(self.upstream), "HEAD",
            cwd=self.fixture)

    def check_generated(self) -> subprocess.CompletedProcess[str]:
        return run(sys.executable, "scripts/check_generated.py", cwd=self.fixture, check=False)

    def commit_fixture(self) -> None:
        if not (self.fixture / ".git").exists():
            init_repository(self.fixture)
        git(self.fixture, "add", "-A")
        git(self.fixture, "commit", "--quiet", "-m", "fixture")

    def test_vendors_whole_directories_with_provenance(self) -> None:
        self.update()
        provenance = json.loads((self.fixture / "src/vendor/skills/provenance.json").read_text())
        self.assertEqual(provenance["commit"], self.commit)
        self.assertEqual(provenance["ref"], "HEAD")
        self.assertEqual(provenance["skills"], self.skills)
        self.assertFalse((self.fixture / "src/vendor/skills/unvendored").exists())
        skill = self.skills[0]
        self.assertEqual(provenance["files"][f"{skill}/scripts/tool"]["mode"], "100755")
        self.assertEqual(provenance["files"][f"{skill}/references/more.md"]["mode"], "100644")
        plugin = next(
            path for path in (self.fixture / "plugins").iterdir() if (path / "skills" / skill).is_dir()
        )
        copied = plugin / "skills" / skill
        self.assertEqual((copied / "references/more.md").read_text(), "# More\n")
        self.assertTrue((copied / "scripts/tool").stat().st_mode & 0o111)
        run(sys.executable, "scripts/validate_manifests.py", cwd=self.fixture)
        self.commit_fixture()
        result = self.check_generated()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_hand_edits_to_vendored_skills(self) -> None:
        self.update()
        self.commit_fixture()
        skill = self.skills[0]
        (self.fixture / f"src/vendor/skills/{skill}/SKILL.md").write_text("edited\n")
        (self.fixture / f"src/vendor/skills/{skill}/references/extra.md").write_text("# Extra\n")
        (self.fixture / f"src/vendor/skills/{skill}/scripts/tool").chmod(0o644)
        result = self.check_generated()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"differs from provenance (edited by hand?): src/vendor/skills/{skill}/SKILL.md", result.stderr)
        self.assertIn(f"vendored file not in provenance: src/vendor/skills/{skill}/references/extra.md", result.stderr)
        self.assertIn(f"mode 100644 differs from provenance: src/vendor/skills/{skill}/scripts/tool", result.stderr)

    def test_rejects_stale_generated_skill_files(self) -> None:
        self.update()
        self.commit_fixture()
        skill = self.skills[0]
        plugin = next(
            path for path in (self.fixture / "plugins").iterdir() if (path / "skills" / skill).is_dir()
        )
        (plugin / "skills" / skill / "references" / "stale.md").write_text("# Stale\n")
        result = self.check_generated()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stale generated skill files", result.stderr)

    def test_rejects_a_skill_both_local_and_vendored(self) -> None:
        self.update()
        skill = self.skills[0]
        local = self.fixture / "src/skills" / skill
        local.mkdir()
        (local / "SKILL.md").write_text(f"---\nname: {skill}\ndescription: Fork.\n---\n")
        result = run(sys.executable, "scripts/generate.py", cwd=self.fixture, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("is in both src/skills/ and src/vendor/skills/", result.stderr)

    def test_rejects_a_missing_upstream_skill(self) -> None:
        shutil.rmtree(self.upstream / "skills" / self.skills[0])
        git(self.upstream, "add", "-A")
        git(self.upstream, "commit", "--quiet", "-m", "remove a skill")
        result = run(sys.executable, "scripts/update-skills.py", "--from-local", str(self.upstream), "HEAD",
                     cwd=self.fixture, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(self.skills[0], result.stderr)


if __name__ == "__main__":
    unittest.main()
