#!/usr/bin/env python3
"""Check an OpenCode (v1.18+ or v2) setup for the compose-preview skills and MCP servers (#42).

  python3 scripts/opencode-check.py                 # read-only checks, no model
  python3 scripts/opencode-check.py --run --project ~/path/to/app [--preview ListScreenPreview]
                                                    # plus a cold and a warm model turn, timed

Prints one line per check (ok / FIX / info). Command output that didn't parse is
saved under $TMPDIR/opencode-check/ (default /tmp) so it can be shared instead of pasted.
"""

import argparse
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
LOGS = Path(os.environ.get("TMPDIR", "/tmp")) / "opencode-check"
SKILLS = ("compose-preview", "compose-ui-builder")
SERVERS = ("compose-preview-mcp", "compose-preview-catalog")
MIN_V1 = (1, 18)
results = []


def report(status: str, message: str) -> None:
    results.append(status)
    print(f"{status:<4} {message}")


def run(opencode: str, args: list, timeout: int = 60, cwd=None) -> tuple:
    # OpenCode takes its workspace (and the MCP roots it sends) from $PWD, not the process cwd;
    # without this the server sees the folder this script was started from (#77).
    env = project_env(str(cwd)) if cwd else None
    try:
        done = subprocess.run([opencode, *args], capture_output=True, text=True,
                              timeout=timeout, cwd=cwd, env=env)
        return done.returncode, done.stdout + done.stderr
    except subprocess.TimeoutExpired as error:
        return 124, f"timed out after {timeout}s\n{error.stdout or ''}"
    except OSError as error:
        return 127, str(error)


def save(name: str, text: str) -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    path = LOGS / f"{name}.log"
    path.write_text(text)
    return path


def check_version(opencode: str) -> None:
    _, out = run(opencode, ["--version"])
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", out)
    version = match.group(0) if match else out.strip()[:40]
    major, minor = (int(match.group(1)), int(match.group(2))) if match else (0, 0)
    if major >= 2:
        report("ok", f"opencode {version} ({opencode})")
    elif (major, minor) >= MIN_V1:
        # 1.18.32 (npm `latest`) parses the v2 `mcp.servers` shape that `mcp install` writes.
        report("ok", f"opencode {version} ({opencode}); v1 accepts the mcp.servers config")
    else:
        report("FIX", f"opencode {version or 'unknown'}: needs 1.18 or later "
                      "(install/upgrade per https://opencode.ai/docs)")


def check_skills(opencode: str) -> None:
    root = HOME / ".agents" / "skills"
    for skill in SKILLS:
        present = (root / skill / "SKILL.md").is_file()
        report("ok" if present else "FIX", f"skill {skill} in {root}" if present else
               f"skill {skill} missing: npx skills add yschimke/skills --global --yes "
               "--skill compose-preview --skill compose-ui-builder")
    code, out = run(opencode, ["debug", "skill"])
    if code != 0:
        report("info", f"`opencode debug skill` unavailable (exit {code}); log {save('debug-skill', out)}")
        return
    for skill in SKILLS:
        # Match the name field: other skills' descriptions mention these names too.
        seen = re.search(rf'"name":\s*"{re.escape(skill)}"', out) is not None
        report("ok" if seen else "FIX", f"opencode discovers skill {skill}" if seen else
               f"opencode does not list skill {skill}; log {save('debug-skill', out)}")


# Installed by scripts/opencode-install.py from the generated opencode/ bundle.
BUNDLE = ("agents/design-reviewer.md", "plugins/compose-preview.js", "skills/harness-notes/SKILL.md")
INSTALL_HINT = ("curl -fsSL https://raw.githubusercontent.com/yschimke/compose-agent-plugins/main/"
                "scripts/opencode-install.py | python3 -")


def check_bundle(opencode: str) -> None:
    base = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "opencode"
    missing = [name for name in BUNDLE if not (base / name).is_file()]
    if missing:
        report("info", f"optional reviewer agent, rules skill or edit reminder missing from {base} "
                       f"({', '.join(missing)}); install: {INSTALL_HINT}")
        return
    report("ok", f"design-reviewer, harness-notes and the edit reminder installed in {base}")
    code, out = run(opencode, ["agent", "list"])
    if code == 0:
        seen = "design-reviewer" in out
        report("ok" if seen else "FIX", "opencode lists the design-reviewer agent" if seen else
               f"opencode does not list design-reviewer; log {save('agent-list', out)}")


def config_files(project) -> list:
    base = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "opencode"
    names = ("opencode.json", "opencode.jsonc", "config.json")
    files = [base / n for n in names]
    if project:
        files += [Path(project) / n for n in names] + [Path(project) / ".opencode" / n for n in names]
    return [f for f in files if f.is_file()]


def check_config(project) -> None:
    files = config_files(project)
    if not files:
        report("FIX", "no opencode config found; run: compose-preview mcp install --opencode")
        return
    text = "\n".join(f.read_text(errors="replace") for f in files)
    report("info", "config: " + ", ".join(str(f) for f in files))
    for server in SERVERS:
        found = f'"{server}"' in text
        if found:
            report("ok", f"{server} configured")
        elif server != "compose-preview-mcp":
            report("info", f"{server} not in config (optional: hosted catalog)")
        else:
            jsonc = next((f for f in files if not is_strict_json(f)), None)
            if jsonc:
                # `mcp install --opencode` refuses to rewrite JSONC, so re-running it can't fix this.
                report("FIX", f"{server} not in config; {jsonc} is JSONC, which "
                              "`compose-preview mcp install --opencode` will not rewrite. "
                              "Merge this into it by hand:")
                print(local_server_snippet())
            else:
                report("FIX", f"{server} not in config (compose-preview mcp install --opencode)")
    check_png_permission(files)


# render_preview's PNGs live in a temporary directory outside the project (#105).
PNG_DIR_RULE = "*/compose-preview-mcp-*"


def check_png_permission(files: list) -> None:
    for path in files:
        try:
            config = json.loads(path.read_text(errors="replace"))
        except ValueError:
            if PNG_DIR_RULE in path.read_text(errors="replace"):
                report("ok", f"external_directory allows {PNG_DIR_RULE} ({path})")
                return
            continue
        permission = config.get("permission") if isinstance(config, dict) else None
        if permission == "allow":
            report("ok", f"permission allows everything ({path})")
            return
        rules = permission.get("external_directory") if isinstance(permission, dict) else None
        if rules == "allow" or (isinstance(rules, dict) and rules.get(PNG_DIR_RULE) == "allow"):
            report("ok", f"external_directory allows {PNG_DIR_RULE} ({path})")
            return
    report("FIX", "OpenCode will ask before reading rendered PNGs, and `opencode run` rejects "
                  "the ask. Merge this into your config:")
    print(png_permission_snippet())


def png_permission_snippet() -> str:
    entry = {"permission": {"external_directory": {PNG_DIR_RULE: "allow"}}}
    return "\n".join("     " + line for line in json.dumps(entry, indent=2).splitlines())


def is_strict_json(path: Path) -> bool:
    if path.suffix == ".jsonc":
        return False
    try:
        json.loads(path.read_text(errors="replace"))
        return True
    except ValueError:
        return False


def local_server_snippet() -> str:
    launcher = shutil.which("compose-preview") or "compose-preview"
    entry = {"servers": {"compose-preview-mcp": {
        "type": "local", "command": [launcher, "mcp", "serve"], "codemode": False}}}
    return "\n".join("     " + line for line in json.dumps({"mcp": entry}, indent=2).splitlines())


def check_mcp_list(opencode: str, project) -> None:
    code, out = run(opencode, ["mcp", "list"], timeout=120, cwd=project)
    if code != 0 and not out.strip():
        report("FIX", f"`opencode mcp list` failed (exit {code})")
        return
    log = save("mcp-list", out)
    for server in SERVERS:
        line = next((l for l in out.splitlines() if server in l), "")
        if not line:
            report("info", f"{server}: not listed")
        elif re.search(r"connected|ready|✓", line, re.I) and not re.search(r"fail|error|disconnect", line, re.I):
            report("ok", f"{server}: {line.strip()[:100]}")
        else:
            report("FIX", f"{server}: {line.strip()[:100]} (log {log})")


def tool_calls(out: str) -> list:
    """Tool calls from `opencode run --format json`, one per callID, in order, final state."""
    calls = {}
    for line in out.splitlines():
        try:
            part = json.loads(line).get("part", {})
        except (ValueError, AttributeError):
            continue
        if not isinstance(part, dict) or part.get("type") != "tool":
            continue
        state = part.get("state") or {}
        error = state.get("error") or (state.get("output") if state.get("status") == "error" else None)
        times = state.get("time") or {}
        took = (times["end"] - times["start"]) / 1000 if {"start", "end"} <= times.keys() else None
        calls[part.get("callID") or len(calls)] = {
            "tool": part.get("tool"), "status": state.get("status"), "input": state.get("input"),
            "seconds": took, "error": " ".join(str(error).split())[:400] if error else None}
    return list(calls.values())


def project_env(project: str) -> dict:
    return {**os.environ, "PWD": project}


def start_server(opencode: str, project: str):
    """`opencode serve` in the project, so both turns share one compose-preview-mcp process.

    Returns (process, url), or (None, reason) when this OpenCode can't attach a run to a server.
    """
    _, help_text = run(opencode, ["run", "--help"], cwd=project)
    if "--attach" not in help_text:
        return None, "`opencode run` has no --attach"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    LOGS.mkdir(parents=True, exist_ok=True)
    log = open(LOGS / "serve.log", "w")
    server = subprocess.Popen([opencode, "serve", "--hostname", "127.0.0.1", "--port", str(port)],
                              cwd=project, env=project_env(project), stdin=subprocess.DEVNULL,
                              stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    deadline = time.time() + 60
    while time.time() < deadline and server.poll() is None:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
            return server, f"http://127.0.0.1:{port}"
        except OSError:
            time.sleep(0.5)
    stop_server(server)
    return None, f"`opencode serve` did not listen on {port} (log {LOGS / 'serve.log'})"


def stop_server(server) -> None:
    if server and server.poll() is None:
        os.killpg(server.pid, signal.SIGTERM)
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(server.pid, signal.SIGKILL)


def model_turn(opencode: str, project: str, preview: str, turn: int, name: str, attach) -> tuple:
    """One timed `opencode run` turn. Returns (elapsed seconds, tool calls)."""
    prompt = (f"render the {preview} preview with the compose-preview-mcp render_preview tool "
              "(inline=false), then reply with 2 bullets and the pngPath")
    attach_args = ["--attach", attach] if attach else []
    start = time.time()
    code, out = run(opencode, ["run", *attach_args, "--format", "json", prompt], timeout=600, cwd=project)
    if code != 0 and "format" in out.lower():  # older/other CLI without --format json
        code, out = run(opencode, ["run", *attach_args, prompt], timeout=600, cwd=project)
    elapsed = time.time() - start
    log = save(f"run-{turn}", out)
    calls = tool_calls(out)
    tools = [call["tool"] for call in calls] or re.findall(r'"tool"\s*:\s*"([^"]+)"', out)
    rendered = "render_preview" in out and re.search(r"\.png", out) is not None
    report("ok" if rendered else "FIX",
           f"{name}: {elapsed:.0f}s, exit {code}, render {'seen' if rendered else 'NOT seen'}; log {log}")
    if tools:
        report("info", f"  tool calls ({len(tools)}): {', '.join(tools[:12])}")
    in_tools = sum(call["seconds"] or 0 for call in calls)
    if in_tools:
        # Splits a missed budget between the render itself and the model's own turns.
        timed = ", ".join(f"{call['tool']} {call['seconds']:.1f}s" for call in calls if call["seconds"] is not None)
        report("info", f"  time in tools {in_tools:.1f}s ({timed}); model and startup {elapsed - in_tools:.1f}s")
    for call in calls:
        if call["status"] == "error":
            report("FIX", f"  {call['tool']} {json.dumps(call['input'])} failed: {call['error']}")
    return elapsed, tools


def model_turns(opencode: str, project: str, preview: str) -> None:
    """T1 then T2 from evals/token-budget.md: a cold render, then the same prompt warm.

    A plain `opencode run` starts its own compose-preview-mcp, so every such turn is cold. Both
    turns attach to one `opencode serve` instead; the second runs in a new session so the model
    renders again rather than answering from the first turn, but against the warm server.
    """
    server, attach = start_server(opencode, project)
    if not server:
        report("info", f"{attach}; both turns start their own server, so turn 2 is not warm")
        attach = None
    try:
        cold, cold_tools = model_turn(opencode, project, preview, 1, "turn 1 (cold, T1)", attach)
        warm, warm_tools = model_turn(opencode, project, preview, 2,
                                      "turn 2 (warm, T2)" if server else "turn 2 (cold again)", attach)
    finally:
        stop_server(server)
    cold_misses = budget_misses(cold_tools)
    report("info" if cold_misses else "ok",
           f"T1 budget (render first, ≤3 calls; time recorded, not judged): "
           f"{'missed: ' + '; '.join(cold_misses) if cold_misses else 'met'} ({len(cold_tools)} calls, {cold:.0f}s)")
    if server:
        warm_misses = budget_misses(warm_tools) + ([f"{warm:.0f}s > 30 s"] if warm > 30 else [])
        report("info" if warm_misses else "ok",
               f"T2 budget (render first, ≤3 calls, ≤30 s, #39): "
               f"{'missed: ' + '; '.join(warm_misses) if warm_misses else 'met'} ({len(warm_tools)} calls, {warm:.0f}s)")


def budget_misses(tools: list) -> list:
    """The call rules evals/token-budget.md holds T1 and T2 to: the render first, and 3 or fewer calls."""
    misses = []
    if tools and not tools[0].endswith("render_preview"):
        misses.append(f"first call was {tools[0]}, not render_preview")
    if len(tools) > 3:
        misses.append(f"{len(tools)} calls > 3")
    return misses


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--opencode", default=shutil.which("opencode"), help="opencode binary")
    parser.add_argument("--project", help="Gradle project with @Previews (needed for --run)")
    parser.add_argument("--preview", default="ListScreenPreview")
    parser.add_argument("--run", action="store_true", help="also run two timed model turns (cold, then warm)")
    args = parser.parse_args()
    project = str(Path(args.project).expanduser()) if args.project else None

    print("OpenCode check (#42)")
    if not args.opencode:
        report("FIX", "opencode not on PATH (install: https://opencode.ai/docs)")
        sys.exit(1)
    check_version(args.opencode)
    report("ok" if shutil.which("compose-preview") else "FIX",
           "compose-preview CLI on PATH" if shutil.which("compose-preview") else
           "compose-preview not on PATH (compose-preview update / open a new terminal)")
    check_skills(args.opencode)
    check_bundle(args.opencode)
    check_config(project)
    check_mcp_list(args.opencode, project)
    if args.run:
        if not project:
            report("FIX", "--run needs --project <gradle project>")
        else:
            model_turns(args.opencode, project, args.preview)
    else:
        print("\nNext: add --run --project <app> for a timed cold and warm render turn.")
    print(f"Logs: {LOGS}")
    sys.exit(1 if "FIX" in results else 0)


if __name__ == "__main__":
    main()
