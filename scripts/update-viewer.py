#!/usr/bin/env python3
"""Move the bundled Compose Preview viewer to a compose-preview-mcp release.

    python3 scripts/update-viewer.py v4.0.0

Downloads that release's `compose-preview-viewer.html` and
`compose-preview-viewer.provenance.json` assets, checks the viewer's sha256
against the provenance, and writes both into src/assets/. The provenance names
the compose-preview-mcp release and, under `source`, the compose-preview-server
release, commit and path the viewer's bytes come from. It then names the release
in the fallback doc and README and regenerates the plugins.

The viewer is never edited here: it is compose-preview-server's page, which
compose-preview-mcp re-publishes byte for byte with each release.
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
REPOSITORY = "https://github.com/yschimke/compose-preview-mcp"
TAG = re.compile(r"^v\d+\.\d+\.\d+$")
# Every place that names the bundled release in prose; the provenance file is the record.
RELEASE_MENTIONS = (
    ASSETS / "compose-preview-viewer-fallback.md",
    ROOT / "README.md",
)
MENTION = re.compile(r"(`?)compose-preview-(?:mcp|server)(`? )v\d+\.\d+\.\d+")


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "compose-agent-plugins"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def main(argv: list[str]) -> None:
    if len(argv) != 2 or not TAG.fullmatch(argv[1]):
        sys.exit("usage: update-viewer.py vX.Y.Z")
    tag = argv[1]
    base = f"{REPOSITORY}/releases/download/{tag}"
    viewer = fetch(f"{base}/compose-preview-viewer.html")
    provenance = json.loads(fetch(f"{base}/compose-preview-viewer.provenance.json"))
    if provenance.get("release") != tag or provenance.get("repository") != REPOSITORY:
        sys.exit(f"{base}/compose-preview-viewer.provenance.json describes another release")
    if hashlib.sha256(viewer).hexdigest() != provenance.get("sha256"):
        sys.exit(f"{tag}'s viewer does not match its provenance sha256")
    previous = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    VIEWER.write_bytes(viewer)
    PROVENANCE.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    for path in RELEASE_MENTIONS:
        text = path.read_text(encoding="utf-8")
        text = MENTION.sub(rf"\g<1>compose-preview-mcp\g<2>{tag}", text)
        path.write_text(text, encoding="utf-8")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "generate.py")], check=True)
    print(f"viewer {previous['release']} -> {tag} ({provenance['sha256'][:12]})")


if __name__ == "__main__":
    main(sys.argv)
