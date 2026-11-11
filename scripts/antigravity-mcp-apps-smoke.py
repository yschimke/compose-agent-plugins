#!/usr/bin/env python3
"""Prepare and summarize an Antigravity v2.31+ MCP Apps and file-viewer smoke.

Run from a checkout:

  python3 scripts/antigravity-mcp-apps-smoke.py               # manual viewer clicks
  python3 scripts/antigravity-mcp-apps-smoke.py --auto-probe  # zero viewer clicks (agent-friendly)
  python3 scripts/antigravity-mcp-apps-smoke.py --check-only  # non-interactive fixture + smoke check
  python3 scripts/antigravity-mcp-apps-smoke.py --logs-dir /tmp

Antigravity v2.30.0 rolled out MCP Apps in the Side Panel Extensions tab, and
v2.31.0 added local file save support for MCP App file viewers. This helper
prepares the dependency-free spike fixture (`spike/p1` and `spike/p2`), stages
scratch `.uid` and `.rc` probe files, guides the live desktop verification (or
prints a ready-to-paste local agent prompt with `--auto-probe`), and summarizes
the `/tmp/spike-*.json` server and bridge reports afterward.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPIKE_SCHEMA = "https://antigravity.google/schemas/v1/plugin.json"


def report(status: str, message: str, results: list[str]) -> None:
    results.append(status)
    print(f"{status:<4} {message}")


def check_and_prepare(
    results: list[str],
    *,
    auto_probe: bool = False,
    auto_probe_message: bool = False,
) -> None:
    prepare = ROOT / "spike" / "prepare.py"
    smoke = ROOT / "spike" / "run-protocol-smoke.py"
    for script in (prepare, smoke):
        if not script.is_file():
            report("FIX", f"missing {script.relative_to(ROOT)}", results)
            return

    prepare_cmd = [sys.executable, str(prepare)]
    if auto_probe:
        prepare_cmd.append("--auto-probe")
    if auto_probe_message:
        prepare_cmd.append("--auto-probe-message")
    completed_prepare = subprocess.run(
        prepare_cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed_prepare.returncode != 0:
        detail = (completed_prepare.stderr or completed_prepare.stdout).strip()
        report("FIX", f"spike/prepare.py failed: {detail}", results)
        return
    mode_note = " (with --auto-probe)" if (auto_probe or auto_probe_message) else ""
    report("ok", f"prepared spike/p1 and spike/p2 Antigravity fixtures{mode_note}", results)

    for plugin_name, server_name in (("p1", "alpha"), ("p2", "beta")):
        plugin_root = ROOT / "spike" / plugin_name
        manifest_path = plugin_root / "plugin.json"
        mcp_path = plugin_root / "mcp_config.json"
        server_path = plugin_root / "echo-mcp" / "server.py"
        if not manifest_path.is_file() or not mcp_path.is_file() or not server_path.is_file():
            report("FIX", f"{plugin_name}: missing prepared manifest, mcp_config.json, or server.py", results)
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("$schema") != SPIKE_SCHEMA or manifest.get("name") != plugin_name:
            report("FIX", f"{plugin_name}: unexpected plugin.json {manifest!r}", results)
        else:
            report("ok", f"{plugin_name}: root plugin.json ready ({SPIKE_SCHEMA})", results)
        mcp_config = json.loads(mcp_path.read_text(encoding="utf-8"))
        servers = mcp_config.get("mcpServers") or {}
        if server_name not in servers:
            report("FIX", f"{plugin_name}: mcp_config.json missing server {server_name!r}", results)
        else:
            server_args = servers[server_name].get("args") or []
            if (auto_probe or auto_probe_message) and "--auto-probe" not in server_args:
                report("FIX", f"{plugin_name}: mcp_config.json missing --auto-probe arg", results)
            else:
                report("ok", f"{plugin_name}: mcp_config.json wires {server_name} -> {server_path.name}", results)

    shipping_manifest = ROOT / "plugins" / "compose-preview" / "plugin.json"
    shipping_mcp = ROOT / "plugins" / "compose-preview" / "mcp_config.json"
    if shipping_manifest.is_file() and shipping_mcp.is_file():
        mcp_data = json.loads(shipping_mcp.read_text(encoding="utf-8")).get("mcpServers") or {}
        if "compose-preview-mcp" in mcp_data and "compose-preview-catalog" in mcp_data:
            report("ok", "compose-preview: Antigravity plugin.json + mcp_config.json present", results)
        else:
            report("FIX", "compose-preview: missing expected MCP servers in mcp_config.json", results)
    else:
        report("FIX", "compose-preview: missing generated Antigravity manifest (run generate.py)", results)

    completed_smoke = subprocess.run(
        [sys.executable, str(smoke)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed_smoke.returncode != 0:
        detail = (completed_smoke.stderr or completed_smoke.stdout).strip()
        report("FIX", f"spike/run-protocol-smoke.py failed: {detail}", results)
    else:
        report("ok", "protocol baseline passed (MCP Apps + open_file + viewer_report)", results)

    agy_bin = shutil.which("agy")
    if agy_bin:
        report("ok", f"agy CLI on PATH: {agy_bin}", results)
    else:
        report("info", "agy CLI not on PATH here (expected on remote CI/VMs; needed on desktop)", results)


def summarize_log_file(path: Path) -> list[str]:
    lines = [f"--- {path} ---"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        lines.append(f"  unreadable JSON: {error}")
        return lines

    client = data.get("clientInfo") or {}
    lines.append(
        f"  server={data.get('serverName')!r} "
        f"autoProbe={bool(data.get('autoProbe'))} "
        f"client={client.get('name')!r}@{client.get('version')!r} "
        f"protocolVersion={data.get('protocolVersion')!r}"
    )
    capabilities = data.get("capabilities")
    cap_keys = sorted(capabilities) if isinstance(capabilities, dict) else []
    lines.append(f"  client capability keys: {cap_keys}")
    lines.append(f"  io.modelcontextprotocol/ui: {json.dumps(data.get('mcpAppsExtension'))}")

    env = data.get("detectionEnvironment") or {}
    if env:
        lines.append(f"  detectionEnvironment: {json.dumps(env, sort_keys=True)}")

    events = data.get("events") if isinstance(data.get("events"), list) else []
    methods = [str(event.get("method")) for event in events if isinstance(event, dict)]
    read_uris = [
        event.get("uri")
        for event in events
        if isinstance(event, dict) and event.get("method") == "resources/read"
    ]
    lines.append(f"  server events ({len(methods)}): {', '.join(methods) if methods else 'none'}")
    lines.append(f"  resources/read URIs: {read_uris}")

    viewer_reports = data.get("viewerReports") if isinstance(data.get("viewerReports"), list) else []
    lines.append(f"  viewerReports captured: {len(viewer_reports)}")
    if viewer_reports:
        latest = viewer_reports[-1] if isinstance(viewer_reports[-1], dict) else {}
        bridge = latest.get("report") if isinstance(latest.get("report"), dict) else {}
        init_res = bridge.get("initialize") if isinstance(bridge.get("initialize"), dict) else {}
        lines.append(f"  latest trigger: {bridge.get('lastTrigger')!r}")
        lines.append(f"  ui/initialize hostInfo: {json.dumps(init_res.get('hostInfo'))}")
        lines.append(f"  ui/initialize hostCapabilities: {json.dumps(init_res.get('hostCapabilities'))}")
        if bridge.get("viewerAction") is not None:
            lines.append(f"  viewerAction (tools/call -> status): {json.dumps(bridge.get('viewerAction'))}")
        auto_state = bridge.get("autoProbe")
        if isinstance(auto_state, dict) and auto_state.get("enabled"):
            lines.append(f"  autoProbe state: {json.dumps(auto_state)}")
        tool_result = bridge.get("toolResult")
        if isinstance(tool_result, dict):
            lines.append(
                f"  ui/notifications/tool-result: contentTypes={tool_result.get('contentTypes')} "
                f"structuredContent={json.dumps(tool_result.get('structuredContent'))}"
            )
        file_probe = bridge.get("file") if isinstance(bridge.get("file"), dict) else {}
        if file_probe.get("read") is not None:
            lines.append(f"  file resources/read: {json.dumps(file_probe.get('read'))}")
        if file_probe.get("subscribe") is not None:
            lines.append(f"  file resources/subscribe: {json.dumps(file_probe.get('subscribe'))}")
        if latest.get("requestMeta") is not None:
            lines.append(f"  tools/call host _meta: {json.dumps(latest.get('requestMeta'))}")
        write_attempts = file_probe.get("writeAttempts")
        if write_attempts:
            lines.append(f"  file writeAttempts: {json.dumps(write_attempts)}")
        if bridge.get("resourceUpdates"):
            lines.append(f"  resourceUpdates: {json.dumps(bridge.get('resourceUpdates'))}")
        other_notes = bridge.get("otherNotifications")
        if other_notes:
            lines.append(f"  other host notifications: {json.dumps(other_notes)}")
    return lines


def summarize_logs(logs_dir: Path, *, baseline_mtimes: dict[Path, float] | None = None) -> int:
    candidates = sorted(logs_dir.glob("spike-*.json"))
    if baseline_mtimes is not None:
        candidates = [
            path
            for path in candidates
            if path not in baseline_mtimes or path.stat().st_mtime > baseline_mtimes[path]
        ]
    if not candidates:
        print(f"(no matching spike-*.json logs found in {logs_dir})")
        return 0
    for path in candidates:
        for line in summarize_log_file(path):
            print(line)
    return len(candidates)


def stage_probe_files(work: Path) -> tuple[Path, Path]:
    uid_file = work / "sample.uid"
    rc_file = work / "sample.rc"
    uid_file.write_text(
        json.dumps(
            {
                "format": "spike-uid",
                "screen": "AntigravityMcpAppProbe",
                "note": "Open in Antigravity v2.31+ to probe MCP App file viewer and local save.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    rc_file.write_text("RC_PROBE_V1\n", encoding="utf-8")
    return uid_file, rc_file


def print_live_steps(uid_file: Path, rc_file: Path, *, auto_probe: bool) -> None:
    p1_dir = ROOT / "spike" / "p1"
    p2_dir = ROOT / "spike" / "p2"
    print()
    print("== Live Antigravity App v2.31+ MCP Apps & file-viewer steps ==")
    print()
    print("0. Confirm version & Labs settings")
    print("   - Open Antigravity -> About and record exact version (target: v2.31.0+).")
    print("   - Check Settings -> Labs and note whether any MCP Apps / Extensions toggle exists.")
    print()
    print("1. Install the prepared spike fixture plugin(s)")
    print(f"     agy plugin uninstall p1 2>/dev/null; agy plugin install {p1_dir}")
    print(f"     agy plugin install {p2_dir}   # optional: tests colliding tool names (Q2/Q10)")
    print("   Start a new Antigravity chat/session so it spawns the alpha MCP server.")
    print()
    if auto_probe:
        print("2. Agent-driven auto-probe (zero clicks inside the viewer)")
        print("   Paste this prompt into the new local Antigravity chat:")
        print()
        print("   ---")
        print(
            f"   Call alpha's `render_preview` tool, then call alpha's `open_file` tool "
            f'with `{{"file": {{"name": "{uid_file.name}", "resourceUri": "{uid_file.as_uri()}"}}}}`. '
            f"Wait 3 seconds, then run `python3 {ROOT / 'scripts/antigravity-mcp-apps-smoke.py'} --logs-dir /tmp` "
            f"and show the full output plus the contents of `{uid_file}`."
        )
        print("   ---")
        print()
        print("   Note: if Antigravity lazy-mounts the webview, open Side Panel -> Extensions")
        print(f"   (or open {uid_file} in the editor) once — auto-probe runs status, model-context,")
        print("   resources/read, resources/subscribe + touch, and local file save automatically on mount.")
        print()
    else:
        print("2. Probe Side Panel MCP Apps (Q8, Q16, Q17)")
        print('   - In chat, ask: "Call render_preview on alpha."')
        print("   - Confirm the text fallback + 1x1 PNG still appear in chat.")
        print("   - Open Side Panel -> Extensions (or check inline chat) for 'Spike echo viewer'.")
        print("   - Click 'Send viewer action' inside the viewer.")
        print("     (Tests tools/call -> status, ui/message, and auto-saves report to /tmp/spike-*.json.)")
        print()
        print("3. Probe MCP App file viewer + local file save (Antigravity v2.31.0+)")
        print(f"   - Staged .uid probe file: {uid_file}")
        print(f"   - Staged .rc probe file:  {rc_file}")
        print("   - Open sample.uid in Antigravity (or ask the agent to call open_file with")
        print(f'     {{"file": {{"name": "{uid_file.name}", "resourceUri": "{uid_file.as_uri()}"}}}}).')
        print("   - Inside the Spike Design Viewer:")
        print("       a) Click '1. Read file (resources/read)'")
        print("       b) Click '2. Subscribe + echo host _meta'")
        print("       c) Click '3. Save local file...' -> 'Confirm save to local file'")
        print()
    print("Optional: test real Compose Preview MCP App surfaces afterward")
    print("   - Uninstall the spike plugins first:")
    print("       agy plugin uninstall p1 && agy plugin uninstall p2")
    print("   - Install shipping compose-preview:")
    print("       python3 scripts/antigravity-install.py")
    print('   - Ask: "Render a Wear Material 3 EdgeButton preview" and check Side Panel -> Extensions.')
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--auto-probe",
        action="store_true",
        help="enable automatic viewer bridge and scratch-file probes on iframe mount (zero viewer clicks)",
    )
    parser.add_argument(
        "--auto-probe-message",
        action="store_true",
        help="with --auto-probe, also send ui/message automatically on mount",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="prepare spike fixtures and run non-interactive checks only",
    )
    parser.add_argument(
        "--logs-dir",
        type=Path,
        default=None,
        help="summarize existing spike-*.json files in this directory and exit",
    )
    options = parser.parse_args()
    auto_probe = options.auto_probe or options.auto_probe_message

    if options.logs_dir is not None:
        summarize_logs(options.logs_dir)
        return 0

    results: list[str] = []
    print("== 1. Static & protocol checks for Antigravity MCP Apps spike ==")
    check_and_prepare(
        results,
        auto_probe=auto_probe,
        auto_probe_message=options.auto_probe_message,
    )
    failed = any(status == "FIX" for status in results)
    print()
    if failed:
        print("Fix the FIX lines above before running the live Antigravity check.")
        return 1
    print("Static and protocol checks passed.")

    if options.check_only:
        print("Live half skipped (--check-only).")
        return 0

    logs_dir = Path("/tmp")
    baseline_mtimes = {
        path: path.stat().st_mtime for path in logs_dir.glob("spike-*.json") if path.is_file()
    }
    work = Path(tempfile.mkdtemp(prefix="compose-agy-mcp-apps-smoke-"))
    try:
        uid_file, rc_file = stage_probe_files(work)
        before_uid = uid_file.read_text(encoding="utf-8")
        print_live_steps(uid_file, rc_file, auto_probe=auto_probe)
        try:
            input("Press Enter after completing the live Antigravity steps to summarize /tmp/spike-*.json... ")
        except EOFError:
            print("(no TTY; summarizing any new logs and exiting)")

        print()
        print("== Observed /tmp/spike-*.json summary ==")
        summarize_logs(logs_dir, baseline_mtimes=baseline_mtimes)

        after_uid = uid_file.read_text(encoding="utf-8") if uid_file.is_file() else ""
        print()
        if after_uid != before_uid:
            print(f"Local file save CONFIRMED on disk: {uid_file} was updated by the host!")
        else:
            print(f"Staged {uid_file.name} was unchanged on disk (skip if you opened another file).")
        print()
        print("Remember to uninstall spike fixtures when done:")
        print("  agy plugin uninstall p1 && agy plugin uninstall p2")
        print("Record observed results in docs/evidence/ before updating docs/harness-matrix.md.")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
