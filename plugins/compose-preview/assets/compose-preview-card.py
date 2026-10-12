#!/usr/bin/env python3
"""Build an Antigravity preview card from a local render_preview result.

Antigravity shows `<agent-embed src="file://...">` by reading the file into an
`<iframe srcdoc>`, so the viewer can't be handed a URL fragment. Instead this
copies the released viewer and appends the static result as an inline
`<script type="application/json" id="compose-preview-result">` block, which the
viewer (compose-preview-server v3.77.0+) reads in static mode.

Input is the JSON text that `render_preview` returns with `inline=false`:
    {"uri": "...", "pngPath": "...", "widthPx": 1, "heightPx": 1, "sha256": "..."}
or, when the compose-preview-mcp server is not enabled, the `--json` output of
`compose-preview show --preview <Name>` or `compose-preview a11y --preview <Name>`
(one preview; the whole response or one entry of its `previews`). An `a11y` entry
also carries its ATF findings and annotated overlay into the card, so a viewer
with render details shows the same A11y overlay and Audit modes as the MCP card;
the CLI has no layout tree, so the card names layout bounds as unavailable.
Pass it as the only argument. The PNGs are read from disk, so the image bytes
never pass through the model.

Prints the `<agent-embed>` line to paste into the reply. Exits non-zero with a
one-line reason when a card can't be built; the reply then goes without one.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import NoReturn

MAX_STATIC_RESULT_BYTES = 500_000
# Matches compose-preview-server's RenderDetails: the `_meta` key marking a card block as a detail.
DETAIL_META = "composePreview/detail"
MAX_FINDINGS = 200
CLI_LAYOUT_UNAVAILABLE = "the compose-preview CLI has no layout tree; render through compose-preview-mcp"
VIEWER = Path(__file__).resolve().with_name("compose-preview-viewer.html")


def fail(message: str) -> NoReturn:
    print(f"compose-preview-card: {message}; reply without a card", file=sys.stderr)
    sys.exit(2)


def output_dir() -> Path:
    # Antigravity keeps per-conversation artifacts under brain/<conversation id>.
    conversation = os.environ.get("ANTIGRAVITY_CONVERSATION_ID", "").strip()
    if conversation and "/" not in conversation and conversation not in (".", ".."):
        directory = Path.home() / ".gemini" / "antigravity" / "brain" / conversation
        if directory.is_dir():
            return directory
    return Path(tempfile.gettempdir()).resolve()


def png_size(png: bytes) -> tuple[int, int] | None:
    """Width and height from the IHDR chunk, which a valid PNG always starts with."""
    if len(png) < 24 or png[12:16] != b"IHDR":
        return None
    return int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")


def cli_preview(value: object) -> dict | None:
    """The one preview in `compose-preview show/a11y --json` output, as a render-like dict."""
    if isinstance(value, dict) and isinstance(value.get("previews"), list):
        previews = [entry for entry in value["previews"] if isinstance(entry, dict) and entry.get("pngPath")]
        if len(previews) != 1:
            fail(
                f"the CLI output has {len(previews)} rendered previews; "
                "narrow it with --preview <Name> or pass one entry of `previews`"
            )
        value = previews[0]
    if not isinstance(value, dict) or isinstance(value.get("uri"), str) or not isinstance(value.get("id"), str):
        return None
    return value


def parse_bounds(wire: object) -> list[int] | None:
    parts = wire.split(",") if isinstance(wire, str) else []
    try:
        bounds = [int(part.strip()) for part in parts]
    except ValueError:
        return None
    return bounds if len(bounds) == 4 else None


def a11y_details(entry: dict) -> tuple[dict, bytes | None] | None:
    """The card's `a11y` detail from a CLI preview's `dataExtensions.a11y`, plus its overlay PNG."""
    carrier = (entry.get("dataExtensions") or {}).get("a11y")
    payload = carrier.get("payload") if isinstance(carrier, dict) else None
    if not isinstance(payload, dict):
        return None
    raw = [f for f in payload.get("findings") or [] if isinstance(f, dict)]
    raw = [f for f in raw if str(f.get("level", "")).upper() != "NOT_RUN"]
    rank = {"ERROR": 0, "WARNING": 1}
    findings = []
    for finding in sorted(raw, key=lambda f: rank.get(str(f.get("level", "")).upper(), 2))[:MAX_FINDINGS]:
        rule = str(finding.get("type") or "Unknown").rsplit(".", 1)[-1].removesuffix("Check") or "Unknown"
        item = {
            "level": str(finding.get("level") or "INFO").upper(),
            "rule": rule,
            "message": str(finding.get("message") or ""),
        }
        if finding.get("viewDescription"):
            item["node"] = str(finding["viewDescription"])
        bounds = parse_bounds(finding.get("boundsInScreen"))
        if bounds:
            item["bounds"] = bounds
        findings.append(item)
    if findings:
        counts = []
        for level, noun in (("ERROR", "error"), ("WARNING", "warning"), ("INFO", "info")):
            n = sum(1 for f in findings if f["level"] == level)
            if n:
                counts.append(f"{n} info" if noun == "info" else f"{n} {noun}{'' if n == 1 else 's'}")
        rules: dict[str, int] = {}
        for f in findings:
            rules[f["rule"]] = rules.get(f["rule"], 0) + 1
        ordered = sorted(rules.items(), key=lambda item: (-item[1], item[0]))
        summary = f"a11y: {', '.join(counts)} ({', '.join(f'{k} ×{v}' for k, v in ordered)})"
    else:
        summary = "a11y: no findings"
    overlay = None
    annotated = payload.get("annotatedPath")
    if isinstance(annotated, str) and Path(annotated).is_file():
        candidate = Path(annotated).read_bytes()
        if candidate.startswith(b"\x89PNG\r\n\x1a\n"):
            overlay = candidate
    return {"summary": summary, "findings": findings}, overlay


def build_envelope(render: dict, png: bytes) -> dict:
    summary = {
        key: render[key]
        for key in ("uri", "id", "widthPx", "heightPx", "sha256")
        if key in render
    }
    content = [
        {
            "type": "image",
            "data": base64.b64encode(png).decode("ascii"),
            "mimeType": "image/png",
        },
        {"type": "text", "text": json.dumps(summary, separators=(",", ":"))},
    ]
    if "uri" not in render:
        # A CLI render: carry its a11y data into the same detail blocks render_preview writes.
        details: dict = {"unavailable": {"layout": CLI_LAYOUT_UNAVAILABLE}}
        a11y = a11y_details(render)
        if a11y:
            details["a11y"], overlay = a11y
            if overlay:
                content.append(
                    {
                        "type": "image",
                        "data": base64.b64encode(overlay).decode("ascii"),
                        "mimeType": "image/png",
                        "_meta": {DETAIL_META: "a11y/overlay"},
                    }
                )
        content.insert(
            2,
            {
                "type": "text",
                "text": json.dumps(details, separators=(",", ":"), ensure_ascii=False),
                "_meta": {DETAIL_META: "details"},
            },
        )
    return {
        "version": 1,
        "arguments": {"uri": render["uri"]} if "uri" in render else {},
        "result": {"content": content},
    }


def inline_block(envelope: dict) -> str:
    payload = json.dumps(envelope, separators=(",", ":"), ensure_ascii=False)
    if len(payload.encode("utf-8")) > MAX_STATIC_RESULT_BYTES:
        fail("the render is too large for a card (over 500,000 bytes)")
    # `<` for every `<` keeps `</script>` and `<!--` out of the block;
    # JSON.parse turns it back into `<`.
    payload = payload.replace("<", "\\u003c")
    return (
        '<script type="application/json" id="compose-preview-result">'
        f"{payload}</script>\n"
    )


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        fail("pass the render_preview inline=false JSON text as the only argument")
    try:
        render = json.loads(argv[1])
    except json.JSONDecodeError:
        fail("the argument is not the render_preview JSON text")
    render = cli_preview(render) or render
    if not isinstance(render, dict) or not (
        isinstance(render.get("uri"), str) or isinstance(render.get("id"), str)
    ):
        fail("the render result has no uri")
    png_path = render.get("pngPath")
    if not isinstance(png_path, str) or not Path(png_path).is_file():
        fail("the render result has no readable pngPath (call render_preview with inline=false)")
    png = Path(png_path).read_bytes()
    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        fail("pngPath is not a PNG")
    expected = render.get("sha256")
    if isinstance(expected, str) and hashlib.sha256(png).hexdigest() != expected.lower():
        fail("the PNG on disk no longer matches the render's sha256")
    if "uri" not in render and "widthPx" not in render:
        size = png_size(png)
        if size:
            render = dict(render, widthPx=size[0], heightPx=size[1])
    if not VIEWER.is_file():
        fail(f"viewer not found at {VIEWER}")

    viewer = VIEWER.read_text(encoding="utf-8")
    card = viewer + inline_block(build_envelope(render, png))
    digest = hashlib.sha256(png).hexdigest()[:12]
    target = output_dir() / f"compose-preview-card-{digest}.html"
    target.write_text(card, encoding="utf-8")
    print(f'<agent-embed src="{target.as_uri()}"></agent-embed>')


if __name__ == "__main__":
    main(sys.argv)
