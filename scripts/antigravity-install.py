#!/usr/bin/env python3
"""Install or update the Compose plugin in Antigravity from GitHub (#39).

Run from anywhere; no checkout needed:
  python3 scripts/antigravity-install.py              # compose-preview
  python3 scripts/antigravity-install.py --catalogs   # compose-catalogs instead (no Java)
  python3 scripts/antigravity-install.py --dry-run    # print the agy commands only

compose-preview carries the local and hosted MCP servers and the compose-preview
and compose-ui-builder skills. compose-catalogs carries only the hosted server and
compose-ui-builder, for a machine without Java; it replaces compose-preview, and the
default replaces it, so the two never coexist. The old skill bundles
(yschimke-skills, compose-skills) are removed too. The optional compose-review
plugin is left as it is.

Antigravity copies a plugin at install time, an install over an existing one
kept its old record, and the bare repository URL adds a second, MCP-only
compose-preview. So each plugin is uninstalled until `agy plugin list` no
longer shows it, then installed from its /tree/main/plugins/<name> URL. Then
stale `compose-preview mcp serve` processes are stopped; restart Antigravity after.
"""

import json
import shutil
import subprocess
import sys

PLUGINS = "https://github.com/yschimke/compose-agent-plugins/tree/main/plugins"
# The two alternatives; each replaces the other.
TARGETS = ("compose-preview", "compose-catalogs")
# Old installs whose skills the plugins now carry.
REPLACED = ("yschimke-skills", "compose-skills")
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
    wanted = "compose-catalogs" if "--catalogs" in sys.argv else "compose-preview"
    for name in (*REPLACED, *TARGETS):
        remove(name)
    agy("install", f"{PLUGINS}/{wanted}")
    agy("enable", wanted)
    if not DRY_RUN and shutil.which("pkill"):
        subprocess.run(["pkill", "-f", "compose-preview.*mcp serve"], check=False)
    if DRY_RUN:
        return
    final = imports()
    entries = [e for e in final if e.get("name") == wanted]
    problems = [] if len(entries) == 1 and entries[0].get("source") == "antigravity" else [f"{wanted}: {entries}"]
    problems += [f"{name}: {e}" for e in final for name in (*REPLACED, *TARGETS)
                 if e.get("name") == name and name != wanted]
    if problems:
        sys.exit("unexpected `agy plugin list` entries:\n  " + "\n  ".join(problems))
    ask = ("render <one of your previews>" if wanted == "compose-preview"
           else "show the available Compose component catalogs")
    print(f"\nInstalled {wanted}. Restart Antigravity, then in a new session ask: {ask}.")


if __name__ == "__main__":
    main()
