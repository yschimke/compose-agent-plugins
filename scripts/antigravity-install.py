#!/usr/bin/env python3
"""Install or update the Compose plugins in Antigravity from GitHub (#39).

Run from anywhere; no checkout needed:
  python3 scripts/antigravity-install.py              # compose-skills + compose-preview
  python3 scripts/antigravity-install.py --catalogs   # also compose-catalogs
  python3 scripts/antigravity-install.py --dry-run    # print the agy commands only

Antigravity copies a plugin at install time, an install over an existing one
kept its old record, and the bare repository URL adds a second, MCP-only
compose-preview. So each plugin is uninstalled until `agy plugin list` no
longer shows it, then installed from its /tree/main/plugins/<name> URL.
compose-catalogs is kept when it was already installed. Then stale
`compose-preview mcp serve` processes are stopped; restart Antigravity after.
"""

import json
import shutil
import subprocess
import sys

SKILLS = "https://github.com/yschimke/skills/tree/main/plugins"
PLUGINS = "https://github.com/yschimke/compose-agent-plugins/tree/main/plugins"
# name -> install URL, in install order.
TARGETS = {
    "compose-skills": f"{SKILLS}/compose-skills",
    "compose-preview": f"{PLUGINS}/compose-preview",
    "compose-catalogs": f"{PLUGINS}/compose-catalogs",
}
# Old installs that duplicate a target: every skill, under the root plugin.
REPLACED = ("yschimke-skills",)
MAX_UNINSTALLS = 5
OPTIONS = {"--catalogs", "--dry-run"}
DRY_RUN = "--dry-run" in sys.argv


def agy(*args: str) -> str:
    command = ["agy", "plugin", *args]
    if args[0] != "list":
        print("$ " + " ".join(command))
    if DRY_RUN and args[0] != "list":
        return ""
    result = subprocess.run(command, capture_output=True, text=True)
    output = (result.stdout + result.stderr).strip()
    if args[0] != "list" and output:
        print("  " + output.replace("\n", "\n  "))
    if result.returncode != 0 and args[0] in ("install", "list"):
        sys.exit(f"agy plugin {args[0]} failed (exit {result.returncode})")
    return output


def imports() -> list[dict]:
    listing = agy("list")
    if "no imported plugins" in listing.lower():  # agy 1.2.x prints this instead of JSON when empty
        return []
    if "{" not in listing and "[" not in listing:
        listing = agy("list", "--json")
    try:
        start = min(i for i in (listing.find("{"), listing.find("[")) if i >= 0)
        parsed = json.loads(listing[start:])
        if isinstance(parsed, list):
            return [entry for entry in parsed if isinstance(entry, dict)]
        return parsed.get("imports", parsed.get("plugins", []))
    except (ValueError, AttributeError):
        sys.exit("could not read `agy plugin list` output")


def names() -> list[str]:
    return [entry.get("name") for entry in imports()]


def remove(name: str) -> None:
    for _ in range(MAX_UNINSTALLS):
        if name not in names():
            return
        agy("uninstall", name)
        if DRY_RUN:
            return
    sys.exit(f"{name} is still listed after {MAX_UNINSTALLS} uninstalls; remove it by hand")


def main() -> None:
    # A mistyped --dry-run must not fall through to a real reinstall.
    unknown = [arg for arg in sys.argv[1:] if arg not in OPTIONS]
    if unknown:
        sys.exit(f"unknown option {unknown[0]}; usage: antigravity-install.py [--catalogs] [--dry-run]")
    if not shutil.which("agy"):
        sys.exit("agy is not on PATH")
    installed = names()
    wanted = ["compose-skills", "compose-preview"]
    if "--catalogs" in sys.argv or "compose-catalogs" in installed:
        wanted.append("compose-catalogs")
    for name in (*REPLACED, *wanted):
        remove(name)
    for name in wanted:
        agy("install", TARGETS[name])
    agy("enable", "compose-preview")
    if not DRY_RUN and shutil.which("pkill"):
        subprocess.run(["pkill", "-f", "compose-preview.*mcp serve"], check=False)
    if DRY_RUN:
        return
    final = imports()
    problems = []
    for name in wanted:
        entries = [e for e in final if e.get("name") == name]
        if len(entries) != 1 or entries[0].get("source") != "antigravity":
            problems.append(f"{name}: {entries}")
    if problems:
        sys.exit("unexpected `agy plugin list` entries:\n  " + "\n  ".join(problems))
    print(f"\nInstalled {', '.join(wanted)}. Restart Antigravity, then in a new session"
          " ask: render <one of your previews>.")


if __name__ == "__main__":
    main()
