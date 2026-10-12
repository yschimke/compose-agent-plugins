#!/usr/bin/env python3
"""Check compose-preview-card.py builds a viewer card with an inline result block."""

import base64
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "plugins" / "compose-preview" / "assets" / "compose-preview-card.py"
VIEWER = HELPER.with_name("compose-preview-viewer.html")


def png(width: int, height: int, extra: bytes = b"") -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))
    body = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    if extra:
        body += chunk(b"tEXt", extra)
    return b"\x89PNG\r\n\x1a\n" + body + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def run(argument: str, home: Path, conversation: str = "") -> subprocess.CompletedProcess:
    # A relative TMPDIR still has to produce an absolute file:// URI.
    env = dict(os.environ, HOME=str(home), TMPDIR="tmp")
    env.pop("ANTIGRAVITY_CONVERSATION_ID", None)
    if conversation:
        env["ANTIGRAVITY_CONVERSATION_ID"] = conversation
    return subprocess.run(
        [sys.executable, str(HELPER), argument], capture_output=True, text=True, env=env, cwd=home
    )


with tempfile.TemporaryDirectory() as tmp:
    home = Path(tmp)
    (home / "tmp").mkdir()
    brain = home / ".gemini" / "antigravity" / "brain" / "conv-1"
    brain.mkdir(parents=True)

    # A text chunk carrying `</script>` proves the block can't be closed early.
    image = png(4, 3, b"Comment\x00</script><script>alert(1)</script><!--")
    image_path = home / "render.png"
    image_path.write_bytes(image)
    sha = hashlib.sha256(image).hexdigest()
    render = {
        "uri": "compose-preview://ws/_app/com.example.PreviewKt.Sample_Devices - Small Round",
        "pngPath": str(image_path),
        "widthPx": 4,
        "heightPx": 3,
        "sha256": sha,
        "changed": True,
        "durationMs": 12,
    }

    result = run(json.dumps(render), home, "conv-1")
    assert result.returncode == 0, result.stderr
    card = brain / f"compose-preview-card-{sha[:12]}.html"
    assert result.stdout.strip() == f'<agent-embed src="{card.as_uri()}"></agent-embed>', result.stdout
    html = card.read_text(encoding="utf-8")
    viewer = VIEWER.read_text(encoding="utf-8")
    assert html.startswith(viewer), "the viewer is copied unchanged"
    block = html[len(viewer):]
    match = re.fullmatch(
        r'<script type="application/json" id="compose-preview-result">(.*)</script>\n',
        block,
        re.S,
    )
    assert match, block[:200]
    payload = match.group(1)
    assert "<" not in payload, "every < is escaped"
    envelope = json.loads(payload)
    assert envelope["version"] == 1
    assert envelope["arguments"] == {"uri": render["uri"]}
    image_block, text_block = envelope["result"]["content"]
    assert image_block == {
        "type": "image",
        "data": base64.b64encode(image).decode("ascii"),
        "mimeType": "image/png",
    }
    assert json.loads(text_block["text"]) == {
        "uri": render["uri"],
        "widthPx": 4,
        "heightPx": 3,
        "sha256": sha,
    }
    assert "pngPath" not in payload

    # Outside Antigravity the card goes to the temp dir.
    result = run(json.dumps(render), home)
    assert result.returncode == 0, result.stderr
    assert (home / "tmp" / card.name).is_file()
    assert result.stdout.strip() == f'<agent-embed src="{(home / "tmp" / card.name).resolve().as_uri()}"></agent-embed>'

    # Refusals: each exits 2 with a reason and writes nothing.
    def refused(argument: str, reason: str) -> None:
        result = run(argument, home, "conv-1")
        assert result.returncode == 2, (argument, result)
        assert reason in result.stderr, result.stderr
        assert result.stdout == ""

    refused("not json", "not the render_preview JSON text")
    refused(json.dumps({"pngPath": str(image_path)}), "no uri")
    refused(json.dumps(dict(render, pngPath=None)), "no readable pngPath")
    refused(json.dumps(dict(render, sha256="0" * 64)), "no longer matches")
    not_png = home / "not.png"
    not_png.write_bytes(b"GIF89a")
    refused(json.dumps(dict(render, pngPath=str(not_png), sha256=None)), "not a PNG")
    big = png(1, 1, b"Comment\x00" + os.urandom(400_000).hex().encode()[:400_000])
    big_path = home / "big.png"
    big_path.write_bytes(big)
    refused(
        json.dumps(dict(render, pngPath=str(big_path), sha256=hashlib.sha256(big).hexdigest())),
        "too large",
    )

    # Without the MCP server: `compose-preview a11y --preview <Name> --json` output builds the same
    # card, with the findings and overlay as render details and layout named as unavailable.
    overlay = png(4, 3, b"Comment\x00overlay")
    overlay_path = home / "overlay.png"
    overlay_path.write_bytes(overlay)
    preview = {
        "id": "com.example.PreviewKt.Sample_Devices - Small Round",
        "module": ":app",
        "pngPath": str(image_path),
        "sha256": sha,
        "dataExtensions": {
            "a11y": {
                "schema": "a11y/v1",
                "payload": {
                    "previewId": "Sample",
                    "annotatedPath": str(overlay_path),
                    "findings": [
                        {"level": "WARNING", "type": "TextContrastCheck", "message": "Low contrast."},
                        {
                            "level": "ERROR",
                            "type": "TouchTargetSizeCheck",
                            "message": "41dp tall.",
                            "viewDescription": "android.view.View",
                            "boundsInScreen": "68,369,386,450",
                        },
                        {"level": "NOT_RUN", "type": "SpeakableTextPresentCheck", "message": ""},
                    ],
                },
            }
        },
    }

    def cli_envelope(argument: str) -> dict:
        result = run(argument, home, "conv-1")
        assert result.returncode == 0, result.stderr
        block = card.read_text(encoding="utf-8")[len(VIEWER.read_text(encoding="utf-8")):]
        match = re.fullmatch(r'<script type="application/json" id="compose-preview-result">(.*)</script>\n', block, re.S)
        assert match, block[:200]
        return json.loads(match.group(1))

    for argument in (
        json.dumps({"schema": "compose-preview-show/v1", "previews": [preview]}),
        json.dumps(preview),
    ):
        envelope = cli_envelope(argument)
        assert envelope["arguments"] == {}
        image_block, text_block, details_block, overlay_block = envelope["result"]["content"]
        assert image_block["data"] == base64.b64encode(image).decode("ascii")
        assert json.loads(text_block["text"]) == {
            "id": preview["id"],
            "widthPx": 4,
            "heightPx": 3,
            "sha256": sha,
        }
        assert details_block["_meta"] == {"composePreview/detail": "details"}
        details = json.loads(details_block["text"])
        assert details["unavailable"] == {"layout": "the compose-preview CLI has no layout tree; render through compose-preview-mcp"}
        assert details["a11y"]["summary"] == "a11y: 1 error, 1 warning (TextContrast ×1, TouchTargetSize ×1)"
        assert details["a11y"]["findings"] == [
            {"level": "ERROR", "rule": "TouchTargetSize", "message": "41dp tall.", "node": "android.view.View", "bounds": [68, 369, 386, 450]},
            {"level": "WARNING", "rule": "TextContrast", "message": "Low contrast."},
        ]
        assert overlay_block["_meta"] == {"composePreview/detail": "a11y/overlay"}
        assert overlay_block["data"] == base64.b64encode(overlay).decode("ascii")

    # `show` without the a11y extension: no a11y detail, no overlay; layout still named.
    plain = {key: value for key, value in preview.items() if key != "dataExtensions"}
    content = cli_envelope(json.dumps({"previews": [plain]}))["result"]["content"]
    assert len(content) == 3
    assert json.loads(content[2]["text"]) == {"unavailable": {"layout": "the compose-preview CLI has no layout tree; render through compose-preview-mcp"}}

    refused(
        json.dumps({"previews": [preview, dict(preview, id="Other")]}),
        "has 2 rendered previews",
    )

print("card helper tests passed")
