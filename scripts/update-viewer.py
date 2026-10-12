#!/usr/bin/env python3
"""Move the bundled Compose Preview viewer to a compose-preview-server release.

    python3 scripts/update-viewer.py v3.131.0

Downloads that release's `compose-preview-viewer.html` asset byte for byte into
src/assets/, records its tag, the commit that last changed the viewer source and
its sha256 in the provenance file, names the release in the fallback doc and
README, then regenerates the plugins.
The viewer is never edited here: a change to it is a compose-preview-server
release first.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src" / "assets"
VIEWER = ASSETS / "compose-preview-viewer.html"
PROVENANCE = ASSETS / "compose-preview-viewer.provenance.json"
REPOSITORY = "https://github.com/yschimke/compose-preview-server"
API = "https://api.github.com/repos/yschimke/compose-preview-server"
TAG = re.compile(r"^v\d+\.\d+\.\d+$")
# Every place that names the bundled release in prose; the provenance file is the record.
RELEASE_MENTIONS = (
    ASSETS / "compose-preview-viewer-fallback.md",
    ROOT / "README.md",
)
MENTION = re.compile(r"(compose-preview-server`? )v\d+\.\d+\.\d+")


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "compose-agent-plugins"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def source_commit(tag: str, path: str) -> str:
    """The last commit at [tag] that changed the viewer's source file."""
    commits = json.loads(fetch(f"{API}/commits?sha={tag}&path={path}&per_page=1"))
    if not commits:
        sys.exit(f"{tag} has no commit touching {path}")
    return commits[0]["sha"]


def main(argv: list[str]) -> None:
    if len(argv) != 2 or not TAG.fullmatch(argv[1]):
        sys.exit("usage: update-viewer.py vX.Y.Z")
    tag = argv[1]
    asset = f"{REPOSITORY}/releases/download/{tag}/compose-preview-viewer.html"
    viewer = fetch(asset)
    protocol = re.search(rb"protocolVersion: '([0-9-]+)',", viewer)
    if protocol is None:
        sys.exit(f"{asset} names no MCP Apps protocolVersion; is it the viewer?")
    previous = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    provenance = {
        "repository": REPOSITORY,
        "release": tag,
        "releaseAsset": asset,
        "commit": source_commit(tag, previous["path"]),
        "path": previous["path"],
        "mcpAppsProtocolVersion": protocol.group(1).decode("ascii"),
        "sha256": hashlib.sha256(viewer).hexdigest(),
    }
    VIEWER.write_bytes(viewer)
    PROVENANCE.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    for path in RELEASE_MENTIONS:
        text = path.read_text(encoding="utf-8")
        path.write_text(MENTION.sub(rf"\g<1>{tag}", text), encoding="utf-8")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "generate.py")], check=True)
    print(f"viewer {previous['release']} -> {tag} ({provenance['sha256'][:12]})")


if __name__ == "__main__":
    main(sys.argv)
