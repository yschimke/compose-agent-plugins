#!/usr/bin/env python3
"""Check an Antigravity install of these plugins against #39. Read-only.

Run from a checkout:  python3 scripts/antigravity-check.py
Prints one line per check (ok / FIX / info), then the manual steps left.
"""

import filecmp
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = Path.home()
INSTALLED = HOME / ".gemini" / "config" / "plugins"
# compose-preview is the default; compose-catalogs replaces it on a machine without Java.
ALTERNATIVES = ("compose-preview", "compose-catalogs")
OPTIONAL = ("compose-review",)
PLUGINS = (*ALTERNATIVES, *OPTIONAL)
# Old skill bundles whose skills the plugins now carry: a second copy of every skill.
RETIRED = ("compose-skills", "yschimke-skills")
REPO_URL = "https://github.com/yschimke/compose-agent-plugins/tree/main/plugins"
results = []


def report(status: str, message: str) -> None:
    results.append(status)
    print(f"{status:<4} {message}")


def run(command: list[str], timeout: int = 20) -> str:
    try:
        return subprocess.run(
            command, capture_output=True, text=True, timeout=timeout
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def check_agy() -> None:
    version = run(["agy", "--version"]) if shutil.which("agy") else ""
    report("ok" if version else "FIX", f"agy: {version or 'not on PATH'}")


def differing_files(left: Path, right: Path) -> list[str]:
    compare = filecmp.dircmp(
        left,
        right,
        ignore=[".generated-assets.json", ".generated-agents.json", ".generated-sidecars.json"],
    )
    found = [f"{name} (only in checkout)" for name in compare.left_only]
    found += compare.diff_files
    for name, sub in compare.subdirs.items():
        found += [f"{name}/{item}" for item in differing_files(left / name, right / name)]
    return found


def check_plugins() -> None:
    present = [name for name in ALTERNATIVES if (INSTALLED / name).is_dir()]
    if not present:
        report("FIX", f"compose-preview: not installed (agy plugin install {REPO_URL}/compose-preview)")
    elif len(present) > 1:
        report("FIX", "compose-preview and compose-catalogs are both installed; compose-preview already "
                      "carries the hosted server: agy plugin uninstall compose-catalogs")
    for name in RETIRED:
        if (INSTALLED / name).is_dir():
            report("FIX", f"{name}: a retired skill bundle that duplicates the plugin's skills; "
                          f"agy plugin uninstall {name}")
    for name in PLUGINS:
        installed = INSTALLED / name
        if not installed.is_dir():
            if name in OPTIONAL:
                report("info", f"{name}: not installed (optional: agy plugin install {REPO_URL}/{name})")
            continue
        stale = differing_files(ROOT / "plugins" / name, installed)
        if stale:
            report("FIX", f"{name}: differs from this checkout ({', '.join(stale[:3])}…); reinstall with agy plugin install {REPO_URL}/{name}")
        else:
            report("ok", f"{name}: installed copy matches this checkout")
    if "compose-preview" not in present:
        return
    helper = INSTALLED / "compose-preview" / "assets" / "compose-preview-card.py"
    report("ok" if helper.is_file() else "FIX", f"card helper: {helper}")
    sidecar = INSTALLED / "compose-preview" / "sidecars" / "compose-preview" / "sidecar.json"
    launcher = INSTALLED / "compose-preview" / "sidecars" / "launch.mjs"
    if sidecar.is_file() and launcher.is_file():
        report("ok", f"Compose Preview sidecar: {sidecar}")
    else:
        report("FIX", f"Compose Preview sidecar missing: reinstall with agy plugin install {REPO_URL}/compose-preview")
    hooks = INSTALLED / "compose-preview" / "hooks.json"
    if hooks.is_file():
        report("ok", f"hooks.json (SessionStart + Stop gate): {hooks} (Stop gate runs with COMPOSE_PREVIEW_GATE=1)")
    else:
        report("FIX", f"hooks.json missing: reinstall with agy plugin install {REPO_URL}/compose-preview")


def check_validate() -> None:
    if shutil.which("agy"):
        for name in PLUGINS:
            raw = run(["agy", "plugin", "validate", "--json", str(ROOT / "plugins" / name)])
            if not raw:
                continue
            try:
                validated = json.loads(raw)
            except ValueError:
                continue
            errors = [
                f.get("message", "")
                for f in validated.get("findings", [])
                if isinstance(f, dict) and f.get("severity") == "error"
            ]
            if errors:
                report("FIX", f"agy plugin validate {name}: {'; '.join(errors)}")
            else:
                components = validated.get("components", {})
                report(
                    "ok",
                    f"agy plugin validate {name}: skills={components.get('skills', 0)}, "
                    f"mcpServers={components.get('mcpServers', 0)}, "
                    f"hooks={components.get('hooks', 0)}, "
                    f"sidecars={components.get('sidecars', 0)}",
                )


def check_imports() -> None:
    """The bare repository URL imports gemini-extension.json: MCP servers only (#39)."""
    listing = run(["agy", "plugin", "list"]) if shutil.which("agy") else ""
    try:
        imports = json.loads(listing[listing.index("{"):]).get("imports", [])
    except (ValueError, AttributeError):
        return
    for entry in imports:
        if entry.get("name") in PLUGINS and entry.get("source") == "gemini-cli":
            report("FIX", f"{entry['name']}: a gemini-cli import (MCP servers only) from the bare repository URL; "
                          f"agy plugin uninstall {entry['name']}, then agy plugin install {REPO_URL}/{entry['name']}")


def check_helper() -> None:
    helper = INSTALLED / "compose-preview" / "assets" / "compose-preview-card.py"
    if not helper.is_file():
        return
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00")) + chunk(b"IEND", b""))
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "x.png"
        path.write_bytes(png)
        render = {"uri": "compose-preview://check/x", "pngPath": str(path), "widthPx": 1,
                  "heightPx": 1, "sha256": hashlib.sha256(png).hexdigest()}
        env = {k: v for k, v in os.environ.items() if k != "ANTIGRAVITY_CONVERSATION_ID"}
        env["TMPDIR"] = tmp
        out = subprocess.run([sys.executable, str(helper), json.dumps(render)],
                             capture_output=True, text=True, env=env, timeout=20)
        ok = out.returncode == 0 and out.stdout.startswith("<agent-embed src=\"file://")
        report("ok" if ok else "FIX", "card helper smoke test" + ("" if ok else f": {out.stderr.strip()}"))


def mcp_probe(command: list[str]) -> tuple[dict, dict]:
    """initialize + tools/list over stdio; returns (initialize result, render_preview schema)."""
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True)
    replies: dict = {}

    def reader() -> None:
        for line in process.stdout:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "id" in message:
                replies[message["id"]] = message

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()

    def send(message: dict) -> None:
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "antigravity-check", "version": "1"}}})
        for _ in range(600):
            if 1 in replies:
                break
            threading.Event().wait(0.1)
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        for _ in range(600):
            if 2 in replies:
                break
            threading.Event().wait(0.1)
    finally:
        process.kill()
    init = replies.get(1, {}).get("result", {})
    tools = replies.get(2, {}).get("result", {}).get("tools", [])
    schema = next((t.get("inputSchema", {}) for t in tools if t.get("name") == "render_preview"), {})
    return init, schema


def check_cli() -> None:
    cli = shutil.which("compose-preview")
    if not cli:
        fallback = HOME / ".local" / "bin" / "compose-preview"
        if fallback.is_file() and os.access(fallback, os.X_OK):
            cli = str(fallback)
    if not cli:
        report("FIX", "compose-preview: not on PATH (open a new terminal, or compose-preview update)")
        return
    report("ok", f"compose-preview: {run([cli, '--version']) or cli}")
    try:
        init, schema = mcp_probe([cli, "mcp", "serve"])
    except OSError as error:
        report("FIX", f"mcp serve: {error}")
        return
    if not init:
        report("FIX", "mcp serve: no initialize reply within 60 s")
        return
    server = init.get("serverInfo", {})
    report("info", f"mcp serve: {server.get('name')} {server.get('version')}")
    properties = schema.get("properties", {})
    missing = [name for name in ("preview", "project") if name not in properties]
    report("FIX" if missing else "ok",
           f"render_preview has no {', '.join(missing)} parameter; the one-call render needs it (update the CLI)"
           if missing else "render_preview accepts preview= and project=")
    report("ok" if init.get("instructions") else "info",
           "initialize instructions: " + ("present" if init.get("instructions") else "none (compose-preview-server#1163)"))


def check_config() -> None:
    for path in (HOME / ".gemini" / "antigravity" / "mcp_config.json",
                 HOME / ".gemini" / "config" / "mcp_config.json"):
        try:
            servers = json.loads(path.read_text()).get("mcpServers", {})
        except (OSError, ValueError, AttributeError):
            continue
        duplicates = [name for name in servers if name.startswith("compose-preview")]
        if duplicates:
            report("FIX", f"{path}: global {', '.join(duplicates)} duplicates the plugin's server; remove it")
    lines = [line for line in run(["ps", "-axo", "pid=,command="]).splitlines()
             if "compose-preview" in line and "mcp serve" in line]
    versions = {m.group(1) for line in lines for m in [re.search(r"compose-preview-(\d+\.\d+\.\d+)", line)] if m}
    if len(versions) > 1:
        report("FIX", f"mcp serve processes from several CLI versions ({', '.join(sorted(versions))}); kill the old ones")
    else:
        report("info", f"mcp serve processes running: {len(lines)}")


def main() -> None:
    print(f"Antigravity check (#39), checkout {ROOT}")
    check_agy()
    check_plugins()
    check_validate()
    check_imports()
    check_helper()
    check_cli()
    check_config()
    print("\nManual, in a new Antigravity session (#39 Verify):")
    print("  1. Open your Compose project and ask: render <one of your previews, e.g. ListScreenPreview>")
    print("  2. Expect: one render_preview call with preview= and project=, a look at the PNG,")
    print("     then the server's embed card + bullets. A first call may return pending once (cold Gradle build).")
    print("  3. Note tool calls and wall time; share the transcript if it takes more than 3 calls or 30 s.")
    sys.exit(1 if "FIX" in results else 0)


if __name__ == "__main__":
    main()
