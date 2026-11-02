#!/usr/bin/env python3
"""Prepare and drive a Cursor live smoke for preview + audit (#79).

Run from a checkout:

  python3 scripts/cursor-smoke.py              # static checks, then pause for live steps
  python3 scripts/cursor-smoke.py --check-only # static checks only (no echo server)
  python3 scripts/cursor-smoke.py --echo-port 8765

Static checks cover generated Cursor manifests, marketplace logo, empty inline
hooks, the design-reviewer agent, and the COMPOSE_PREVIEW_TOKEN variable. The
live half is preview- and audit-first: install, Reload, render a local or
catalog @Preview, confirm a11y/guidelines audit tools, and note MCP App shell
behaviour. UI Builder is out of scope for this smoke.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAMES = ("compose-preview", "compose-catalogs", "compose-review")
LOGO = "compose-preview-logo.png"


class _HeaderEcho(BaseHTTPRequestHandler):
    """Minimal Streamable HTTP MCP stub that logs X-Compose-Preview-Token."""

    log_path: Path

    def log_message(self, *_args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        self.send_response(405)
        self.end_headers()

    def do_DELETE(self) -> None:  # noqa: N802
        self.send_response(200)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            body = {}
        token = self.headers.get("X-Compose-Preview-Token")
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"method": body.get("method"), "token": token}) + "\n")
        if "id" not in body:
            self.send_response(202)
            self.end_headers()
            return
        result: dict[str, object] = {}
        method = body.get("method")
        if method == "initialize":
            params = body.get("params") if isinstance(body.get("params"), dict) else {}
            result = {
                "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "header-echo", "version": "0"},
            }
        elif method == "tools/list":
            result = {"tools": []}
        elif method == "notifications/initialized":
            self.send_response(202)
            self.end_headers()
            return
        payload = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": result}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def report(status: str, message: str, results: list[str]) -> None:
    results.append(status)
    print(f"{status:<4} {message}")


REQUIRED_MARKETPLACE_FIELDS = (
    "name",
    "displayName",
    "description",
    "license",
    "version",
    "author",
)


def check_manifests(results: list[str]) -> None:
    marketplace = ROOT / ".cursor-plugin" / "marketplace.json"
    if not marketplace.is_file():
        report("FIX", f"missing {marketplace.relative_to(ROOT)}", results)
    else:
        data = json.loads(marketplace.read_text(encoding="utf-8"))
        names = [entry.get("name") for entry in data.get("plugins", [])]
        report("ok", f"marketplace plugins: {', '.join(str(n) for n in names)}", results)
        if not data.get("name") or not (data.get("owner") or {}).get("name"):
            report("FIX", "marketplace.json needs name and owner.name", results)
        else:
            report("ok", f"marketplace name={data['name']!r} owner={data['owner']['name']!r}", results)

    for name in PLUGIN_NAMES:
        plugin_root = ROOT / "plugins" / name
        manifest_path = plugin_root / ".cursor-plugin" / "plugin.json"
        if not manifest_path.is_file():
            report("FIX", f"{name}: missing .cursor-plugin/plugin.json (run generate.py)", results)
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("name") != name:
            report("FIX", f"{name}: manifest name is {manifest.get('name')!r}", results)

        missing = [field for field in REQUIRED_MARKETPLACE_FIELDS if not manifest.get(field)]
        if missing:
            report("FIX", f"{name}: missing marketplace fields {', '.join(missing)}", results)
        else:
            author = manifest.get("author")
            author_ok = isinstance(author, dict) and bool(author.get("name"))
            if not author_ok:
                report("FIX", f"{name}: author must be an object with name", results)
            else:
                report(
                    "ok",
                    f"{name}: submit fields ok "
                    f"(displayName={manifest['displayName']!r}, version={manifest['version']})",
                    results,
                )
        keywords = manifest.get("keywords")
        if not isinstance(keywords, list) or not keywords:
            report("info", f"{name}: no keywords (optional for submit)", results)
        else:
            report("ok", f"{name}: keywords {', '.join(str(k) for k in keywords)}", results)

        if name in ("compose-preview", "compose-catalogs"):
            logo = manifest.get("logo")
            asset = plugin_root / "assets" / LOGO
            if logo == f"./assets/{LOGO}" and asset.is_file() and asset.stat().st_size > 0:
                report("ok", f"{name}: marketplace logo {logo} ({asset.stat().st_size} bytes)", results)
            else:
                report("FIX", f"{name}: expected logo ./assets/{LOGO} and non-empty file on disk", results)

        if name == "compose-preview":
            hooks = manifest.get("hooks")
            if hooks == {"version": 1, "hooks": {}}:
                report("ok", f"{name}: empty inline hooks (Claude hooks not loaded)", results)
            else:
                report("FIX", f"{name}: expected empty inline hooks, found {hooks!r}", results)
            servers = manifest.get("mcpServers") or {}
            if "compose-preview-mcp" in servers and "compose-preview-catalog" in servers:
                report("ok", f"{name}: local + hosted MCP servers", results)
            else:
                report("FIX", f"{name}: need both compose-preview-mcp and catalog", results)
            variables = (manifest.get("variables") or {}).get("properties") or {}
            if "COMPOSE_PREVIEW_TOKEN" in variables:
                report("ok", f"{name}: COMPOSE_PREVIEW_TOKEN variable declared", results)
            else:
                report("FIX", f"{name}: COMPOSE_PREVIEW_TOKEN missing from variables", results)
            catalog = servers.get("compose-preview-catalog") if isinstance(servers, dict) else None
            header = None
            if isinstance(catalog, dict):
                header = (catalog.get("headers") or {}).get("X-Compose-Preview-Token")
            if header == "${COMPOSE_PREVIEW_TOKEN}":
                report("ok", f"{name}: catalog header uses ${{COMPOSE_PREVIEW_TOKEN}}", results)
            else:
                report("FIX", f"{name}: catalog token header is {header!r}", results)
            reviewer = plugin_root / "agents" / "design-reviewer.md"
            if reviewer.is_file():
                report("ok", f"{name}: agents/design-reviewer.md present", results)
            else:
                report("FIX", f"{name}: missing agents/design-reviewer.md", results)
            skill = plugin_root / "skills" / "compose-preview" / "SKILL.md"
            if skill.is_file():
                report("ok", f"{name}: compose-preview skill present", results)
            else:
                report("FIX", f"{name}: missing compose-preview skill", results)

        if name == "compose-review":
            for skill_name in ("compose-preview-review", "compose-preview-ci"):
                path = plugin_root / "skills" / skill_name / "SKILL.md"
                if path.is_file():
                    report("ok", f"{name}: {skill_name} skill present", results)
                else:
                    report("FIX", f"{name}: missing {skill_name}", results)


def validate_schemas(results: list[str], work: Path) -> None:
    """Optional: validate against Cursor's published schemas when npm/git work."""
    if shutil.which("npm") is None or shutil.which("git") is None:
        report("info", "skip schema validate (need git + npm); CI covers this", results)
        return
    schemas = work / "cursor-plugins"
    print(f"$ git clone --depth 1 --filter=blob:none --sparse https://github.com/cursor/plugins {schemas}")
    try:
        subprocess.run(
            ["git", "clone", "-q", "--depth", "1", "--filter=blob:none", "--sparse",
             "https://github.com/cursor/plugins", str(schemas)],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "-C", str(schemas), "sparse-checkout", "set", "schemas"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        report("info", f"skip schema clone ({error.stderr.strip() or error})", results)
        return
    ajv_prefix = work / "ajv"
    try:
        subprocess.run(
            ["npm", "install", "--silent", "--no-save", "--prefix", str(ajv_prefix),
             "ajv-cli@5", "ajv-formats@3"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        report("info", f"skip ajv install ({error.stderr.strip() or error})", results)
        return
    ajv = ajv_prefix / "node_modules" / ".bin" / "ajv"
    schema_root = schemas / "schemas"

    def run_ajv(schema: Path, document: Path) -> None:
        completed = subprocess.run(
            [str(ajv), "validate", "--spec=draft7", "--strict=false",
             "-c", str(ajv_prefix / "node_modules" / "ajv-formats"),
             "-s", str(schema), "-d", str(document)],
            capture_output=True,
            text=True,
            check=False,
        )
        rel = document.relative_to(ROOT)
        if completed.returncode == 0:
            report("ok", f"schema ok: {rel}", results)
        else:
            detail = (completed.stderr or completed.stdout).strip()
            report("FIX", f"schema fail: {rel}: {detail}", results)

    run_ajv(schema_root / "marketplace.schema.json", ROOT / ".cursor-plugin" / "marketplace.json")
    for name in PLUGIN_NAMES:
        run_ajv(
            schema_root / "plugin.schema.json",
            ROOT / "plugins" / name / ".cursor-plugin" / "plugin.json",
        )


def prepare_echo_plugin(work: Path, port: int) -> Path:
    """Copy compose-catalogs with catalog URL pointed at the local echo server."""
    source = ROOT / "plugins" / "compose-catalogs"
    destination = work / "echo-plugin" / "compose-catalogs"
    shutil.copytree(source, destination)
    manifest_path = destination / ".cursor-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    servers = manifest.setdefault("mcpServers", {})
    catalog = servers.setdefault("compose-preview-catalog", {})
    catalog["url"] = f"http://127.0.0.1:{port}/mcp"
    catalog["type"] = "http"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return destination


def start_echo(log_path: Path, port: int) -> tuple[HTTPServer, threading.Thread]:
    _HeaderEcho.log_path = log_path
    server = HTTPServer(("127.0.0.1", port), _HeaderEcho)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def print_live_steps(*, echo_plugin: Path | None, port: int) -> None:
    print()
    print("== Live Cursor steps (preview + audit; skip UI Builder for this smoke) ==")
    print()
    print("1. Install the real plugin from this checkout:")
    print("     python3 scripts/cursor-install.py")
    print("   Optional PR-review skills alongside it:")
    print("     python3 scripts/cursor-install.py --review")
    print("   Developer: Reload Window. Customize should list compose-preview,")
    print("   compose-preview + compose-ui-builder skills, design-reviewer, and both MCP servers.")
    print()
    print("2. Preview render")
    print("   - Hosted (no Java): ask \"render a Wear Material 3 EdgeButton large-round\"")
    print("     (or any catalog_render_preview). Confirm PNG + text in the tool result.")
    print("   - Local (CLI on PATH): open a Compose project and ask")
    print('     \"render the ListScreenPreview\" (one of your @Preview names).')
    print("   - MCP App: note whether ui://compose-preview/viewer stays on")
    print('     \"Waiting for a preview result…\". Empty shell is a known host gap;')
    print("     the chat image/text is still the source of truth.")
    print()
    print("3. Audit / review")
    print("   - Ask for accessibility or layout details on that render (a11y / semantics).")
    print("   - Ask: \"Review this preview against its catalog design guidelines\"")
    print("     (preview_guidelines_prompt / design-reviewer). Prefer a local @Preview")
    print("     or a catalog component — not a UI Builder design for this smoke.")
    print("   - Confirm Customize (or agent list) shows design-reviewer.")
    print("   - With --review installed: confirm compose-preview-review /")
    print("     compose-preview-ci skills appear.")
    print()
    print("4. Hooks")
    print("   - Cursor hooks UI should show no compose-preview hooks.")
    print("     The manifest ships empty inline hooks so Claude hooks/hooks.json is ignored.")
    print()
    if echo_plugin is not None:
        print("5. Token expansion (optional echo pass)")
        print("   This temporarily replaces the local install with a catalog whose URL is")
        print("   the echo server. Restore the real plugin before you finish (step 6).")
        print(f"   - Copy {echo_plugin} into ~/.cursor/plugins/local/compose-catalogs")
        print("     (removes/replaces whatever is there), then Developer: Reload Window.")
        print("   - Leave COMPOSE_PREVIEW_TOKEN unset; open a chat that touches the catalog MCP.")
        print("   - Set the plugin variable (or env) to smoke-cursor-token, Reload, retry.")
        print(f"   - Echo listens on http://127.0.0.1:{port}/mcp until this script exits.")
        print()
        print("6. Restore the real plugin (required if you ran step 5)")
        print("   - python3 scripts/cursor-install.py")
        print("     (installs compose-preview and removes the echo compose-catalogs)")
        print("   - Developer: Reload Window before any further Cursor work.")
        print()
    print("7. Cloud Agent (separate from Desktop IDE plugin)")
    print("   - Dashboard MCP: compose-preview-catalog → https://preview.coo.ee/mcp")
    print("   - New agent; confirm status / catalog_list_projects; request_access for PNG.")
    print("   - IDE ~/.cursor/plugins/local does not apply to Cloud Agents.")
    print()
    print("8. Human preview pane (optional)")
    print("   - Extensions: install Compose Preview (yuri-schimke.compose-preview).")
    print("   - Open Compose Preview view; confirm EditorScope follows the active Kotlin file.")
    print()
    print("Record outcomes under docs/evidence/ and update docs/harness-matrix.md.")
    print("Marketplace submit only after this live half passes (#81).")
    print("Repo-side remaining gates: docs/cursor.md#remaining-gates-cursor-optimised")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check-only", action="store_true",
                        help="run static checks only (no echo server, no pause)")
    parser.add_argument("--skip-schema", action="store_true",
                        help="skip cloning Cursor schemas / ajv validate")
    parser.add_argument("--echo-port", type=int, default=8765,
                        help="local echo MCP port (default 8765)")
    options = parser.parse_args()
    results: list[str] = []

    print("== 1. Static Cursor packaging checks ==")
    check_manifests(results)

    work = Path(tempfile.mkdtemp(prefix="compose-cursor-smoke-"))
    server: HTTPServer | None = None
    log_path = work / "headers.log"
    try:
        if not options.skip_schema:
            print()
            print("== 2. Cursor published schemas ==")
            validate_schemas(results, work)

        failed = any(status == "FIX" for status in results)
        print()
        if failed:
            print("Fix the FIX lines (usually: python3 scripts/generate.py), then rerun.")
            return 1
        print("Static checks passed.")

        if options.check_only:
            print("Live half skipped (--check-only).")
            return 0

        log_path.write_text("", encoding="utf-8")
        server, _thread = start_echo(log_path, options.echo_port)
        time.sleep(0.05)
        echo_plugin = prepare_echo_plugin(work, options.echo_port)
        print_live_steps(echo_plugin=echo_plugin, port=options.echo_port)
        try:
            input("Press Enter when the live Cursor steps are done "
                  "(and the real plugin is restored if you used the echo pass)... ")
        except EOFError:
            print("(no TTY; printing echo log and exiting)")

        print()
        print("== Echo server headers ==")
        text = log_path.read_text(encoding="utf-8").strip()
        print(text if text else "(no requests — echo pass skipped or MCP did not connect)")
        print()
        print("If you installed the echo compose-catalogs copy, restore now:")
        print("  python3 scripts/cursor-install.py && Developer: Reload Window")
        print("Leaving the echo plugin installed points the catalog MCP at a dead localhost.")
        return 0
    finally:
        if server is not None:
            server.shutdown()
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
