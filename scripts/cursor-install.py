#!/usr/bin/env python3
"""Install or update the Compose plugin for Cursor (#59).

Run from anywhere; no checkout needed:
  curl -fsSL https://raw.githubusercontent.com/yschimke/compose-agent-plugins/main/scripts/cursor-install.py | python3 -
  python3 scripts/cursor-install.py              # compose-preview
  python3 scripts/cursor-install.py --catalogs   # compose-catalogs instead (no Java)
  python3 scripts/cursor-install.py --dry-run    # print what would change
  python3 scripts/cursor-install.py --plugins-dir DIR

Cursor loads plugins from ~/.cursor/plugins/local/<name> after Developer: Reload
Window (or a restart). Until the public Cursor Marketplace lists this repository
(#59 / #81), that local folder is the one-install path: skills, agents and both
MCP servers from the plugin's .cursor-plugin/plugin.json. compose-catalogs
replaces compose-preview on a machine without Java; the two never coexist.
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

REPO = "yschimke/compose-agent-plugins"
ARCHIVE = "https://github.com/{repo}/archive/{ref}.zip"
TARGETS = ("compose-preview", "compose-catalogs")
# Host-foreign trees Cursor does not need; copying them only confuses a local install.
SKIP_DIR_NAMES = {".codex-plugin", ".claude-plugin", "__pycache__"}


def default_plugins_dir() -> Path:
    return Path.home() / ".cursor" / "plugins" / "local"


def local_plugin_source(wanted: str) -> Path | None:
    """When this script lives in a checkout, use that checkout's plugins/<wanted>."""
    root = Path(__file__).resolve().parent.parent
    plugin = root / "plugins" / wanted
    if (plugin / ".cursor-plugin" / "plugin.json").is_file():
        return plugin
    return None


def download_plugin(wanted: str, ref: str) -> tuple[Path, Path]:
    """Download the repository archive.

    Returns (plugin_path, staging_root). The caller must delete staging_root.
    """
    url = ARCHIVE.format(repo=REPO, ref=ref)
    print(f"$ curl -fsSL {url}")
    with urllib.request.urlopen(url, timeout=60) as response:
        payload = response.read()
    staging = Path(tempfile.mkdtemp(prefix="compose-cursor-"))
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        archive.extractall(staging)
    tops = [path for path in staging.iterdir() if path.is_dir()]
    if len(tops) != 1:
        shutil.rmtree(staging, ignore_errors=True)
        sys.exit(f"unexpected archive layout under {staging}: {[p.name for p in tops]}")
    plugin = tops[0] / "plugins" / wanted
    if not (plugin / ".cursor-plugin" / "plugin.json").is_file():
        shutil.rmtree(staging, ignore_errors=True)
        sys.exit(f"archive at {ref} has no plugins/{wanted}/.cursor-plugin/plugin.json")
    return plugin, staging


def should_skip(path: Path, root: Path) -> bool:
    return any(part in SKIP_DIR_NAMES for part in path.relative_to(root).parts)


def copy_plugin(source: Path, destination: Path, dry_run: bool) -> None:
    """Replace destination with a copy of source, skipping host-foreign plugin folders."""
    prefix = "would " if dry_run else ""
    if destination.exists() or destination.is_symlink():
        print(f"{prefix}remove {destination}")
        if not dry_run:
            if destination.is_symlink() or destination.is_file():
                destination.unlink()
            else:
                shutil.rmtree(destination)
    print(f"{prefix}copy {source} -> {destination}")
    if dry_run:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    for path in source.rglob("*"):
        if should_skip(path, source):
            continue
        relative = path.relative_to(source)
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def remove_sibling(plugins_dir: Path, name: str, dry_run: bool) -> None:
    path = plugins_dir / name
    if not (path.exists() or path.is_symlink()):
        return
    prefix = "would " if dry_run else ""
    print(f"{prefix}remove {path} (compose-preview and compose-catalogs must not coexist)")
    if dry_run:
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)


def verify(plugins_dir: Path, wanted: str) -> None:
    installed = plugins_dir / wanted
    manifest_path = installed / ".cursor-plugin" / "plugin.json"
    if not manifest_path.is_file():
        sys.exit(f"missing {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("name") != wanted:
        sys.exit(f"{manifest_path} name is {manifest.get('name')!r}, expected {wanted!r}")
    servers = manifest.get("mcpServers")
    if not isinstance(servers, dict) or not servers:
        sys.exit(f"{manifest_path} has no mcpServers")
    if not (installed / "skills").is_dir():
        sys.exit(f"missing skills directory at {installed / 'skills'}")
    other = [name for name in TARGETS if name != wanted and (plugins_dir / name).exists()]
    if other:
        sys.exit(f"also installed: {', '.join(other)}; remove them and rerun")


def next_steps(wanted: str, plugins_dir: Path, *, installed: bool) -> None:
    ask = ("render <one of your previews>" if wanted == "compose-preview"
           else "show the available Compose component catalogs")
    verb = "Installed" if installed else "Would install"
    print(f"\n{verb} {wanted} into {plugins_dir / wanted}.")
    print("Reload Cursor (Developer: Reload Window), open Customize and confirm the plugin,")
    print(f"then in a new chat ask: {ask}.")
    if wanted == "compose-preview" and shutil.which("compose-preview") is None:
        print("Note: local renders need the compose-preview CLI on PATH; the plugin's")
        print("compose-preview-setup skill installs it on first use, or run:")
        print("  curl -fsSL https://raw.githubusercontent.com/yschimke/skills/main/scripts/install.sh | bash")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--catalogs", action="store_true",
                        help="install compose-catalogs instead of compose-preview")
    parser.add_argument("--plugins-dir", type=Path, default=None,
                        help="Cursor local plugins directory (default ~/.cursor/plugins/local)")
    parser.add_argument("--ref", default="main",
                        help="git ref to download when not running from a checkout")
    parser.add_argument("--dry-run", action="store_true")
    options = parser.parse_args()

    wanted = "compose-catalogs" if options.catalogs else "compose-preview"
    plugins_dir = options.plugins_dir or default_plugins_dir()
    source = local_plugin_source(wanted)
    staging: Path | None = None
    try:
        if source is None:
            if options.dry_run:
                print(f"would download plugins/{wanted} from {REPO}@{options.ref}")
                for name in TARGETS:
                    if name != wanted:
                        remove_sibling(plugins_dir, name, dry_run=True)
                print(f"would install into {plugins_dir / wanted}")
                next_steps(wanted, plugins_dir, installed=False)
                return 0
            source, staging = download_plugin(wanted, options.ref)
        for name in TARGETS:
            if name != wanted:
                remove_sibling(plugins_dir, name, options.dry_run)
        copy_plugin(source, plugins_dir / wanted, options.dry_run)
        if options.dry_run:
            next_steps(wanted, plugins_dir, installed=False)
            return 0
        verify(plugins_dir, wanted)
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)

    next_steps(wanted, plugins_dir, installed=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
