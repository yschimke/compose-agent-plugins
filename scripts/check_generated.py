#!/usr/bin/env python3
"""Reject generated-plugin drift without inspecting unrelated working files."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from generate import (
    AGENT_LEDGER_NAME,
    ANTIGRAVITY_HOOK_MANIFEST,
    ASSET_LEDGER_NAME,
    HOOK_MANIFESTS,
    OPENCODE_LEDGER_NAME,
    OPENCODE_ROOT,
    ROOT,
    RULES_TARGET,
    SOURCE,
    hook_script,
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
        paths.extend(plugin_root / "skills" / skill / "SKILL.md" for skill in skills)
        codex_skills, codex_path = codex_skill_config(plugin)
        paths.extend(plugin_root / codex_path / skill / "SKILL.md" for skill in codex_skills)
        agents = plugin.get("agents", [])
        if not isinstance(agents, list) or not all(isinstance(agent, str) for agent in agents):
            raise ValueError(f"{name}.agents must be a list of strings")
        paths.extend(plugin_root / "agents" / f"{agent}.md" for agent in agents)
        if agents:
            paths.append(plugin_root / "agents" / AGENT_LEDGER_NAME)
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


def previous_codex_skill_paths() -> list[Path]:
    """Include generated deletions even when a skill is no longer selected."""
    tracked = git("ls-tree", "-r", "--name-only", "HEAD", "--", "plugins")
    if tracked.returncode:
        raise ValueError(f"could not inspect tracked Codex skills: {tracked.stderr.strip()}")
    return [ROOT / path for path in tracked.stdout.splitlines()
            if len(Path(path).parts) >= 5
            and Path(path).parts[2:4] == (".codex-plugin", "skills")]


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    paths, plugin_names = generated_paths(source)
    paths.extend(previous_hook_paths(source))
    paths.extend(previous_asset_paths(source))
    paths.extend(previous_app_paths(source))
    paths.extend(previous_codex_skill_paths())
    paths = list(dict.fromkeys(paths))
    errors = []

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
