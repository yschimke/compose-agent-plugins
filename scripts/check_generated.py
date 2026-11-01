#!/usr/bin/env python3
"""Reject generated-plugin drift without inspecting unrelated working files."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from generate import (
    AGENT_LEDGER_NAME,
    CLAUDE_AGENT_DIR,
    PORTABLE_AGENT_DIR,
    ANTIGRAVITY_HOOK_MANIFEST,
    ASSET_LEDGER_NAME,
    HOOK_MANIFESTS,
    OPENCODE_LEDGER_NAME,
    OPENCODE_ROOT,
    ROOT,
    RULES_TARGET,
    SIDECAR_LAUNCHER_NAME,
    SIDECAR_LEDGER_NAME,
    SOURCE,
    VENDOR_PROVENANCE,
    VENDOR_SKILL_ROOT,
    SKILL_IGNORED_PARTS,
    hook_script,
    skill_files,
    codex_skill_config,
    render_antigravity_hooks,
    render_opencode_bundle,
)


def generated_paths(source: object) -> tuple[list[Path], set[str]]:
    if not isinstance(source, dict) or not isinstance(source.get("plugins"), list):
        raise ValueError("src/plugins.json plugins must be a list")

    paths = [
        ROOT / ".claude-plugin" / "marketplace.json",
        ROOT / ".cursor-plugin" / "marketplace.json",
        ROOT / "gemini-extension.json",
        ROOT / "server.json",
        OPENCODE_ROOT / OPENCODE_LEDGER_NAME,
    ]
    paths.extend(OPENCODE_ROOT / relative for relative in render_opencode_bundle(source, source["plugins"]))
    plugin_names: set[str] = set()
    for plugin in source["plugins"]:
        if not isinstance(plugin, dict) or not isinstance(plugin.get("name"), str):
            raise ValueError("each plugin must have a name")
        name = plugin["name"]
        if name in plugin_names:
            raise ValueError(f"duplicate plugin name: {name}")
        plugin_names.add(name)
        plugin_root = ROOT / "plugins" / name
        paths.extend(
            (
                plugin_root / "plugin.json",
                plugin_root / ".claude-plugin" / "plugin.json",
                plugin_root / ".codex-plugin" / "plugin.json",
                plugin_root / ".cursor-plugin" / "plugin.json",
                plugin_root / "README.md",
                plugin_root / "LICENSE",
            )
        )
        if plugin.get("mcp"):
            paths.extend((plugin_root / "mcp_config.json", plugin_root / ".mcp.json"))
        if plugin.get("apps"):
            paths.append(plugin_root / ".app.json")
        if plugin.get("rules"):
            paths.append(plugin_root / RULES_TARGET)
        skills = plugin.get("skills", [])
        if not isinstance(skills, list) or not all(isinstance(skill, str) for skill in skills):
            raise ValueError(f"{name}.skills must be a list of strings")
        paths.extend(
            plugin_root / "skills" / skill / relative for skill in skills for relative in skill_files(skill)
        )
        codex_skills, codex_path = codex_skill_config(plugin)
        paths.extend(
            plugin_root / codex_path / skill / relative
            for skill in codex_skills
            for relative in skill_files(skill)
        )
        agents = plugin.get("agents", [])
        if not isinstance(agents, list) or not all(isinstance(agent, str) for agent in agents):
            raise ValueError(f"{name}.agents must be a list of strings")
        for directory in (PORTABLE_AGENT_DIR, CLAUDE_AGENT_DIR):
            paths.extend(plugin_root / directory / f"{agent}.md" for agent in agents)
            if agents:
                paths.append(plugin_root / directory / AGENT_LEDGER_NAME)
        sidecars = plugin.get("sidecars", [])
        if not isinstance(sidecars, list) or not all(isinstance(sidecar, str) for sidecar in sidecars):
            raise ValueError(f"{name}.sidecars must be a list of strings")
        paths.extend(plugin_root / "sidecars" / sidecar / "sidecar.json" for sidecar in sidecars)
        if sidecars:
            paths.append(plugin_root / "sidecars" / SIDECAR_LAUNCHER_NAME)
            paths.append(plugin_root / "sidecars" / SIDECAR_LEDGER_NAME)
        hooks = plugin.get("hooks", [])
        if not isinstance(hooks, list) or not all(isinstance(hook, dict) for hook in hooks):
            raise ValueError(f"{name}.hooks must be a list of objects")
        if hooks:
            paths.extend(plugin_root / manifest for manifest in HOOK_MANIFESTS.values())
            if render_antigravity_hooks(name, hooks):
                paths.append(plugin_root / ANTIGRAVITY_HOOK_MANIFEST)
        for hook in hooks:
            command = hook.get("command")
            if not isinstance(command, str):
                raise ValueError(f"{name}.hooks commands must be strings")
            paths.append(plugin_root / command)
        assets = plugin.get("assets", [])
        if not isinstance(assets, list) or not all(isinstance(asset, str) for asset in assets):
            raise ValueError(f"{name}.assets must be a list of strings")
        paths.extend(plugin_root / "assets" / asset for asset in assets)
        if assets:
            paths.append(plugin_root / "assets" / ASSET_LEDGER_NAME)
    return paths, plugin_names


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=False, text=True, capture_output=True
    )


def previous_hook_paths(source: object) -> list[Path]:
    """Return hook outputs tracked by HEAD, including outputs just deleted by generation."""
    paths: list[Path] = []
    for plugin in source["plugins"]:
        name = plugin["name"]
        # A deleted Antigravity manifest is drift too.
        antigravity_manifest = Path("plugins") / name / ANTIGRAVITY_HOOK_MANIFEST
        if not git("cat-file", "-e", f"HEAD:{antigravity_manifest}").returncode:
            paths.append(ROOT / antigravity_manifest)
        for manifest_path in HOOK_MANIFESTS.values():
            manifest = Path("plugins") / name / manifest_path
            previous = git("show", f"HEAD:{manifest}")
            if previous.returncode:
                continue
            data = json.loads(previous.stdout)
            hooks = data.get("hooks", {})
            if not isinstance(hooks, dict):
                raise ValueError(f"tracked {manifest} hooks must be an object")
            paths.append(ROOT / manifest)
            for entries in hooks.values():
                if not isinstance(entries, list):
                    raise ValueError(f"tracked {manifest} hook entries must be a list")
                for entry in entries:
                    for hook in entry.get("hooks", []):
                        command = hook.get("command")
                        script = hook_script(command) if isinstance(command, str) else None
                        if script:
                            paths.append(ROOT / "plugins" / name / script)
    return paths


def previous_asset_paths(source: object) -> list[Path]:
    """Return asset outputs tracked by HEAD, including a just-deleted final asset and ledger."""
    paths: list[Path] = []
    for plugin in source["plugins"]:
        name = plugin["name"]
        ledger = Path("plugins") / name / "assets" / ASSET_LEDGER_NAME
        previous = git("show", f"HEAD:{ledger}")
        if previous.returncode:
            continue
        data = json.loads(previous.stdout)
        assets = data.get("assets")
        if not isinstance(assets, list) or not all(isinstance(asset, str) for asset in assets):
            raise ValueError(f"tracked {ledger} assets must be a list of strings")
        paths.append(ROOT / ledger)
        paths.extend(ROOT / "plugins" / name / "assets" / asset for asset in assets)
    return paths


def previous_app_paths(source: object) -> list[Path]:
    """Return tracked app manifests so removing an app cannot leave stale generated output."""
    paths: list[Path] = []
    for plugin in source["plugins"]:
        manifest = Path("plugins") / plugin["name"] / ".app.json"
        if not git("cat-file", "-e", f"HEAD:{manifest}").returncode:
            paths.append(ROOT / manifest)
    return paths


def previous_skill_paths() -> list[Path]:
    """Include generated deletions even when a skill, or one of its files, is no longer shipped."""
    tracked = git("ls-tree", "-r", "--name-only", "HEAD", "--", "plugins")
    if tracked.returncode:
        raise ValueError(f"could not inspect tracked skills: {tracked.stderr.strip()}")
    return [ROOT / path for path in tracked.stdout.splitlines()
            if (len(Path(path).parts) >= 5 and Path(path).parts[2:4] == (".codex-plugin", "skills"))
            or (len(Path(path).parts) >= 4 and Path(path).parts[2] == "skills")]


def stale_skill_files(plugin_root: Path, expected: set[Path]) -> list[str]:
    roots = (plugin_root / "skills", plugin_root / ".codex-plugin" / "skills")
    return sorted(
        str(path.relative_to(ROOT))
        for root in roots
        if root.is_dir()
        for path in root.rglob("*")
        if path.is_file()
        and path not in expected
        and not SKILL_IGNORED_PARTS.intersection(path.relative_to(root).parts)
    )


def vendored_skill_errors() -> list[str]:
    """Vendored skills must be exactly what scripts/update-skills.py recorded: no hand edits."""
    if not VENDOR_SKILL_ROOT.exists():
        return []
    if not VENDOR_PROVENANCE.is_file():
        return [f"{VENDOR_PROVENANCE.relative_to(ROOT)} is missing; run scripts/update-skills.py"]
    record = json.loads(VENDOR_PROVENANCE.read_text(encoding="utf-8"))
    recorded = record.get("files")
    skills = record.get("skills")
    if not isinstance(recorded, dict) or not isinstance(skills, list):
        return [f"{VENDOR_PROVENANCE.relative_to(ROOT)} must list skills and files"]
    errors = []
    directories = sorted(path.name for path in VENDOR_SKILL_ROOT.iterdir() if path.is_dir())
    if directories != sorted(skills):
        errors.append(f"vendored skill directories {directories} differ from provenance skills {sorted(skills)}")
    actual = {
        path.relative_to(VENDOR_SKILL_ROOT).as_posix(): path
        for path in VENDOR_SKILL_ROOT.rglob("*")
        if path.is_file()
        and path != VENDOR_PROVENANCE
        and not SKILL_IGNORED_PARTS.intersection(path.relative_to(VENDOR_SKILL_ROOT).parts)
    }
    for relative in sorted(set(actual) - set(recorded)):
        errors.append(f"vendored file not in provenance: src/vendor/skills/{relative}")
    for relative in sorted(set(recorded) - set(actual)):
        errors.append(f"vendored file missing: src/vendor/skills/{relative}")
    for relative in sorted(set(actual) & set(recorded)):
        path, entry = actual[relative], recorded[relative]
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry.get("sha256"):
            errors.append(f"vendored file differs from provenance (edited by hand?): src/vendor/skills/{relative}")
        mode = "100755" if path.stat().st_mode & 0o111 else "100644"
        if mode != entry.get("mode"):
            errors.append(f"vendored file mode {mode} differs from provenance: src/vendor/skills/{relative}")
    if errors:
        errors.append("vendored skills are copied by scripts/update-skills.py <ref>; change them in yschimke/skills")
    return errors


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    paths, plugin_names = generated_paths(source)
    expected_paths = set(paths)
    paths.extend(previous_hook_paths(source))
    paths.extend(previous_asset_paths(source))
    paths.extend(previous_app_paths(source))
    paths.extend(previous_skill_paths())
    paths = list(dict.fromkeys(paths))
    errors = vendored_skill_errors()

    missing = [str(path.relative_to(ROOT)) for path in paths if not path.is_file()]
    if missing:
        errors.append(f"missing generated files: {', '.join(sorted(missing))}")

    plugins_root = ROOT / "plugins"
    actual_dirs = {path.name for path in plugins_root.iterdir() if path.is_dir()}
    stale_dirs = actual_dirs - plugin_names
    if stale_dirs:
        errors.append(f"stale plugin directories: {', '.join(sorted(stale_dirs))}")

    for plugin in source["plugins"]:
        name = plugin["name"]
        stale_skills = stale_skill_files(plugins_root / name, expected_paths)
        if stale_skills:
            errors.append(f"{name} has stale generated skill files: {', '.join(stale_skills)}")
        expected_hooks = {
            Path(hook["command"]).name for hook in plugin.get("hooks", []) if "command" in hook
        }
        scripts_root = plugins_root / name / "scripts"
        actual_hooks = (
            {path.name for path in scripts_root.iterdir() if path.is_file()}
            if scripts_root.is_dir()
            else set()
        )
        stale_hooks = actual_hooks - expected_hooks
        if stale_hooks:
            errors.append(
                f"{name} has stale generated hooks: {', '.join(sorted(stale_hooks))}"
            )
        expected_assets = set(plugin.get("assets", []))
        assets_root = plugins_root / name / "assets"
        actual_assets = (
            {
                path.name
                for path in assets_root.iterdir()
                if path.is_file() and path.name != ASSET_LEDGER_NAME
            }
            if assets_root.is_dir()
            else set()
        )
        stale_assets = actual_assets - expected_assets
        if stale_assets:
            errors.append(
                f"{name} has stale generated assets: {', '.join(sorted(stale_assets))}"
            )

    pathspecs = [str(path.relative_to(ROOT)) for path in paths]
    diff = git("diff", "--exit-code", "--", *pathspecs)
    if diff.returncode:
        errors.append("generated files differ from their checked-out versions")

    status = git("status", "--porcelain", "--untracked-files=all", "--", *pathspecs)
    if status.returncode:
        errors.append(f"could not inspect generated files: {status.stderr.strip()}")
    elif status.stdout:
        errors.append("generated files have untracked or staged changes:\n" + status.stdout.rstrip())

    if errors:
        raise ValueError("\n".join(errors))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"generated plugin check failed: {error}", file=sys.stderr)
        raise SystemExit(1)
