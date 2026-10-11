#!/usr/bin/env python3
"""Install or update the Compose Preview pieces for OpenCode (#8, #42).

Run from anywhere; no checkout needed:
  curl -fsSL https://raw.githubusercontent.com/yschimke/compose-agent-plugins/main/scripts/opencode-install.py | python3 -
  python3 scripts/opencode-install.py --dry-run     # print what would change
  python3 scripts/opencode-install.py --config-dir DIR

OpenCode has no plugin marketplace, so this copies the generated opencode/ bundle into its config
directory (default $XDG_CONFIG_HOME/opencode, else ~/.config/opencode):

  agents/design-reviewer.md         the read-only review subagent
  skills/harness-notes/SKILL.md     the cross-harness agent rules
  plugins/compose-preview.js        the post-edit render reminder

Then it adds the two MCP servers and the rendered-PNG read permission to opencode.json, keeping
every existing key and entry. A JSONC file, or one with comments, is never rewritten: the
snippet to merge by hand is printed instead. The canonical skills come from yschimke/skills:
  npx skills add yschimke/skills --global --yes --skill compose-preview --skill compose-ui-builder
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

RAW = "https://raw.githubusercontent.com/yschimke/compose-agent-plugins/{ref}/opencode/{path}"
LEDGER = ".generated-opencode.json"
CONFIG = "opencode.json"
LOCAL_BUNDLE = Path(__file__).resolve().parent.parent / "opencode" if "__file__" in globals() else None


def read_bundle(ref: str) -> dict[str, bytes]:
    """The bundle's files: from this checkout when run from one, else from GitHub at `ref`."""
    if LOCAL_BUNDLE is not None and (LOCAL_BUNDLE / LEDGER).is_file():
        names = json.loads((LOCAL_BUNDLE / LEDGER).read_text(encoding="utf-8"))
        return {name: (LOCAL_BUNDLE / name).read_bytes() for name in names}

    def fetch(path: str) -> bytes:
        with urllib.request.urlopen(RAW.format(ref=ref, path=path), timeout=30) as response:
            return response.read()

    return {name: fetch(name) for name in json.loads(fetch(LEDGER))}


def merge_config(config: dict, bundle: dict) -> list[str]:
    """Add the bundle's MCP servers and PNG permission to `config` in place; return what changed.

    An existing server entry is kept as it is, under either the v2 `mcp.servers.<name>` or the v1
    `mcp.<name>` shape: `compose-preview mcp install --opencode` writes one with the project path.
    """
    changes = []
    if "$schema" not in config:
        config["$schema"] = bundle["$schema"]
    mcp = config.setdefault("mcp", {})
    if not isinstance(mcp, dict):
        raise ValueError("`mcp` is not an object")
    # A config already in the v1 shape (servers directly under `mcp`) gets v1 entries, without the
    # v2-only `codemode`; mixing in a `servers` key would read as a server of that name.
    v1 = "servers" not in mcp and any(isinstance(entry, dict) and "type" in entry for entry in mcp.values())
    servers = mcp if v1 else mcp.setdefault("servers", {})
    if not isinstance(servers, dict):
        raise ValueError("`mcp.servers` is not an object")
    existing = set(servers) | set(mcp)
    for name, server in bundle["mcp"]["servers"].items():
        if name not in existing:
            servers[name] = {k: v for k, v in server.items() if k != "codemode"} if v1 else server
            changes.append(f"added MCP server {name}")
    # A scalar permission ("ask", "deny") becomes a pattern map that keeps it as the `*` default and
    # adds the PNG rule after it; OpenCode applies the last matching rule. "allow" already covers it.
    permission = config.setdefault("permission", {})
    if isinstance(permission, str) and permission != "allow":
        permission = config["permission"] = {"*": permission, "external_directory": permission}
    if isinstance(permission, dict):
        rules = permission.setdefault("external_directory", permission.get("*", {}))
        if isinstance(rules, str) and rules != "allow":
            rules = permission["external_directory"] = {"*": rules}
        for pattern, action in bundle["permission"]["external_directory"].items():
            if isinstance(rules, dict) and pattern not in rules:
                rules[pattern] = action
                changes.append(f"allowed reading rendered PNGs ({pattern})")
    return changes


def config_status(config_dir: Path) -> tuple[Path, dict | None]:
    """The config file to update and its parsed content, or None when it must not be rewritten."""
    for name in ("opencode.jsonc", CONFIG):
        path = config_dir / name
        if path.is_file():
            if path.suffix == ".jsonc":
                return path, None
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                return path, None
            return path, loaded if isinstance(loaded, dict) else None
    return config_dir / CONFIG, {}


def install(config_dir: Path, bundle_files: dict[str, bytes], dry_run: bool) -> int:
    prefix = "would " if dry_run else ""
    for name, content in sorted(bundle_files.items()):
        if name == CONFIG:
            continue
        target = config_dir / name
        state = "unchanged" if target.is_file() and target.read_bytes() == content else "write"
        if state == "write" and not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        print(f"{'ok  ' if state == 'unchanged' else prefix + 'write'} {target}")

    bundle = json.loads(bundle_files[CONFIG])
    path, config = config_status(config_dir)
    if config is None:
        snippet = {key: bundle[key] for key in ("mcp", "permission")}
        print(f"FIX  {path} is JSONC or has comments, so it is not rewritten. Merge any of this")
        print("     that it lacks by hand (keep an existing compose-preview-mcp entry):")
        print("\n".join("     " + line for line in json.dumps(snippet, indent=2).splitlines()))
        return 1
    changes = merge_config(config, bundle)
    if changes and not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    for change in changes:
        print(f"{prefix}{change} in {path}")
    if not changes:
        print(f"ok   {path} already has both servers and the PNG permission")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    default_dir = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "opencode"
    parser.add_argument("--config-dir", type=Path, default=default_dir)
    parser.add_argument("--ref", default="main", help="git ref to download when not in a checkout")
    parser.add_argument("--dry-run", action="store_true")
    options = parser.parse_args()
    status = install(options.config_dir, read_bundle(options.ref), options.dry_run)
    print("Next: install the canonical skills if you haven't, then restart OpenCode:")
    print("  npx skills add yschimke/skills --global --yes --skill compose-preview --skill compose-ui-builder")
    print("Check with: opencode agent list (design-reviewer) and opencode mcp list")
    return status


if __name__ == "__main__":
    sys.exit(main())
