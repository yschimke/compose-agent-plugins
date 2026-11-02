#!/usr/bin/env python3
"""Check a Cursor local-plugin install of these plugins. Read-only.

Run from a checkout:  python3 scripts/cursor-check.py
                      python3 scripts/cursor-check.py --plugins-dir DIR

Prints one line per check (ok / FIX / info), then the manual steps left.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALTERNATIVES = ("compose-preview", "compose-catalogs")
OPTIONAL = ("compose-review",)
LOGO = "compose-preview-logo.png"
results: list[str] = []


def report(status: str, message: str) -> None:
    results.append(status)
    print(f"{status:<4} {message}")


def check_plugin(plugins_dir: Path, name: str) -> None:
    installed = plugins_dir / name
    if not installed.is_dir():
        return
    manifest_path = installed / ".cursor-plugin" / "plugin.json"
    if not manifest_path.is_file():
        report("FIX", f"{name}: missing .cursor-plugin/plugin.json "
                      f"(rerun scripts/cursor-install.py)")
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError as error:
        report("FIX", f"{name}: invalid plugin.json ({error})")
        return
    if manifest.get("name") != name:
        report("FIX", f"{name}: manifest name is {manifest.get('name')!r}")
    servers = manifest.get("mcpServers")
    if not isinstance(servers, dict) or not servers:
        report("FIX", f"{name}: mcpServers missing from plugin.json")
    else:
        report("ok", f"{name}: mcpServers {', '.join(sorted(servers))}")
    hooks = manifest.get("hooks")
    # compose-preview ships an empty inline hooks object so Cursor does not load
    # the Claude Code hooks/hooks.json next to it.
    if name == "compose-preview":
        if hooks == {"version": 1, "hooks": {}}:
            report("ok", f"{name}: empty inline hooks (Claude hooks not loaded)")
        else:
            report("FIX", f"{name}: expected empty inline hooks, found {hooks!r}")
        reviewer = installed / "agents" / "design-reviewer.md"
        report("ok" if reviewer.is_file() else "FIX",
               f"{name}: design-reviewer agent"
               if reviewer.is_file() else
               f"{name}: missing agents/design-reviewer.md")
    if name in ("compose-preview", "compose-catalogs"):
        logo = manifest.get("logo")
        asset = installed / "assets" / LOGO
        if logo == f"./assets/{LOGO}" and asset.is_file():
            report("ok", f"{name}: marketplace logo present")
        else:
            report("info", f"{name}: no marketplace logo yet "
                           "(rerun scripts/cursor-install.py after generate)")
    skills = installed / "skills"
    if not skills.is_dir():
        report("FIX", f"{name}: no skills/ directory")
    else:
        skill_names = sorted(path.name for path in skills.iterdir() if path.is_dir())
        report("ok", f"{name}: skills {', '.join(skill_names) or '(none)'}")
    checkout = ROOT / "plugins" / name / ".cursor-plugin" / "plugin.json"
    if checkout.is_file():
        expected = json.loads(checkout.read_text(encoding="utf-8"))
        if expected.get("version") != manifest.get("version"):
            report("info", f"{name}: installed version {manifest.get('version')} "
                           f"(checkout has {expected.get('version')}); rerun "
                           "scripts/cursor-install.py to update")
    if (installed / ".claude-plugin").exists() or (installed / ".codex-plugin").exists():
        report("FIX", f"{name}: host-foreign .claude-plugin/.codex-plugin present; "
                      "rerun scripts/cursor-install.py")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--plugins-dir", type=Path,
                        default=Path.home() / ".cursor" / "plugins" / "local")
    options = parser.parse_args()
    plugins_dir = options.plugins_dir

    if not plugins_dir.is_dir():
        report("FIX", f"local plugins dir missing: {plugins_dir} "
                      "(run scripts/cursor-install.py)")
    else:
        report("ok", f"local plugins dir: {plugins_dir}")

    present = [name for name in ALTERNATIVES if (plugins_dir / name).is_dir()]
    if not present:
        report("FIX", "compose-preview: not installed "
                      "(curl -fsSL …/scripts/cursor-install.py | python3 -)")
    elif len(present) > 1:
        report("FIX", "compose-preview and compose-catalogs are both installed; "
                      "compose-preview already carries the hosted server: remove "
                      f"{plugins_dir / 'compose-catalogs'}")
    for name in present:
        check_plugin(plugins_dir, name)
    for name in OPTIONAL:
        if (plugins_dir / name).is_dir():
            check_plugin(plugins_dir, name)
            report("info", f"{name}: optional review plugin is installed")

    if "compose-preview" in present:
        cli = shutil.which("compose-preview")
        report("ok" if cli else "info",
               f"compose-preview CLI: {cli or 'not on PATH (setup skill installs it)'}")

    print()
    if any(status == "FIX" for status in results):
        print("Fix the FIX lines, then Developer: Reload Window in Cursor.")
        return 1
    print("Looks good. In Cursor: Customize should list the plugin and its MCP servers.")
    print("Then ask: render <one of your previews>.")
    print("Audit: review that preview against catalog design guidelines / design-reviewer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
