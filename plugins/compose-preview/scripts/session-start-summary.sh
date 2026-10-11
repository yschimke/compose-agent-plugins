#!/bin/sh
# Emit a safe SessionStart context summary for Claude Code and Codex.
#
# Probe capabilities before invoking them so an older installation remains a
# silent no-op. Every subprocess is bounded independently and receives closed
# stdin, so neither a help probe nor a status command can accidentally become a
# long-running stdio server. Diagnostics may include machine-specific paths,
# configuration details or credentials, so only fixed statuses and integers read
# from the CLI's versioned status envelope are surfaced.

probe_timeout_seconds=3
# The manifest gives the whole hook 10 seconds. Reserve time for cleanup and the final JSON write;
# otherwise several individually valid near-timeout probes can consume the harness deadline before
# the result is emitted.
hook_tick_budget=70
temporary_root=$(mktemp -d "${TMPDIR:-/tmp}/compose-preview-session-start.XXXXXX") || exit 0
probe_pid=

cleanup() {
  if [ -n "$probe_pid" ]; then
    cleanup_probe_pid=$probe_pid
    probe_pid=
    kill "$cleanup_probe_pid" 2>/dev/null || true
    kill -KILL "$cleanup_probe_pid" 2>/dev/null || true
  fi
  rm -rf "$temporary_root"
}

trap 'cleanup' EXIT
trap 'cleanup; exit 129' HUP
trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM

run_probe() {
  probe_output=$1
  probe_marker=$2
  shift 2
  : >"$probe_output"
  rm -f "$probe_marker"

  if [ "$hook_tick_budget" -le 0 ]; then
    : >"$probe_marker"
    return 124
  fi

  "$@" </dev/null >"$probe_output" 2>/dev/null &
  probe_pid=$!
  probe_ticks=0
  probe_tick_limit=$((probe_timeout_seconds * 10))
  if [ "$hook_tick_budget" -lt "$probe_tick_limit" ]; then
    probe_tick_limit=$hook_tick_budget
  fi
  while kill -0 "$probe_pid" 2>/dev/null && [ "$probe_ticks" -lt "$probe_tick_limit" ]; do
    sleep 0.1
    probe_ticks=$((probe_ticks + 1))
    hook_tick_budget=$((hook_tick_budget - 1))
  done
  if kill -0 "$probe_pid" 2>/dev/null; then
    : >"$probe_marker"
    kill "$probe_pid" 2>/dev/null || true
    probe_grace_ticks=0
    while kill -0 "$probe_pid" 2>/dev/null && [ "$probe_grace_ticks" -lt 5 ]; do
      sleep 0.1
      probe_grace_ticks=$((probe_grace_ticks + 1))
    done
    if kill -0 "$probe_pid" 2>/dev/null; then
      kill -KILL "$probe_pid" 2>/dev/null || true
    fi
  fi
  wait "$probe_pid" 2>/dev/null
  probe_status=$?
  probe_pid=

  if [ -f "$probe_marker" ]; then
    return 124
  fi
  return "$probe_status"
}

emit_context() {
  printf '%s\n' "{\"hookSpecificOutput\":{\"hookEventName\":\"SessionStart\",\"additionalContext\":\"$1\"}}"
}

context_message=

append_context() {
  if [ -n "$context_message" ]; then
    context_message="$context_message $1"
  else
    context_message=$1
  fi
}

plural() {
  if [ "$1" -eq 1 ]; then
    printf '%s' "$2"
  else
    printf '%s' "$3"
  fi
}

# Read the versioned `design status --json` envelope (compose-preview-server v3.75.0+) and print
# the fixed SessionStart sentence, or nothing when there is nothing to act on. Only integers are
# taken from the output, so paths, URLs or credentials can never reach the session context.
#
# The server counts a design whose document records no `home` as MISSING_HOME inside `unavailable`.
# Recorded homes are not written yet (compose-preview-server#1157), so today that is every design
# published in the repository. It is not an unsaved copy or an unreachable server, and reporting it
# would warn on every session, so those designs are left out of the unavailable count.
status_summary() {
  status_file=$1
  status_lines=$(wc -l <"$status_file" | tr -d '[:space:]')
  [ "$status_lines" = 1 ] || return 1
  grep -Eq '^\{"schema":"compose-preview-design-status/v1",' "$status_file" || return 1
  status_totals=$(grep -Eo '"totals":\{[^{}]*\}' "$status_file" | sed -n '1p')
  [ -n "$status_totals" ] || return 1
  status_integer='(0|[1-9][0-9]{0,8})'
  for status_key in unacknowledgedComments unsavedTemporaryCopies unavailable; do
    printf '%s\n' "$status_totals" | grep -Eq "[{,]\"$status_key\":${status_integer}[,}]" || return 1
  done
  status_comments=$(printf '%s\n' "$status_totals" | sed -E 's/.*[{,]"unacknowledgedComments":([0-9]+)[,}].*/\1/')
  status_copies=$(printf '%s\n' "$status_totals" | sed -E 's/.*[{,]"unsavedTemporaryCopies":([0-9]+)[,}].*/\1/')
  status_unavailable=$(printf '%s\n' "$status_totals" | sed -E 's/.*[{,]"unavailable":([0-9]+)[,}].*/\1/')
  # Design ids and file names are restricted to [A-Za-z0-9._-], so this code cannot be forged
  # from inside another field.
  status_missing_home=$(grep -Eo '"code":"MISSING_HOME"' "$status_file" | wc -l | tr -d '[:space:]')
  # Server-homed designs come back as REMOTE_UNAVAILABLE whenever the local `serve` is not running,
  # which is routine for people who only start it sometimes. They collapse into one short hint
  # instead of a count that repeats every session.
  status_remote_unavailable=$(grep -Eo '"code":"REMOTE_UNAVAILABLE"' "$status_file" | wc -l | tr -d '[:space:]')
  [ $((status_missing_home + status_remote_unavailable)) -le "$status_unavailable" ] || return 1
  status_unavailable=$((status_unavailable - status_missing_home - status_remote_unavailable))

  status_sentence=
  if [ "$status_comments" -gt 0 ]; then
    status_sentence="$status_comments unacknowledged design $(plural "$status_comments" comment comments)"
  fi
  if [ "$status_copies" -gt 0 ]; then
    status_sentence="${status_sentence:+$status_sentence; }$status_copies unsaved temporary $(plural "$status_copies" copy copies)"
  fi
  if [ "$status_unavailable" -gt 0 ]; then
    status_sentence="${status_sentence:+$status_sentence; }design inventory unavailable for $status_unavailable workspace-linked $(plural "$status_unavailable" design designs)"
  fi
  if [ "$status_remote_unavailable" -gt 0 ]; then
    status_sentence="${status_sentence:+$status_sentence; }design server not running"
  fi
  if [ -n "$status_sentence" ]; then
    printf '%s.\n' "$status_sentence"
  fi
}

workspace_root=${CLAUDE_PROJECT_DIR:-$PWD}

if ! command -v compose-preview >/dev/null 2>&1; then
  emit_context "Compose Preview needs setup: compose-preview is not available on PATH."
  exit 0
fi

help_output="$temporary_root/help.out"
if run_probe "$help_output" "$temporary_root/help.timed-out" compose-preview mcp --help; then
  help_status=0
else
  help_status=$?
fi
if [ "$help_status" -eq 124 ]; then
  # A probe that outlasts its bound says nothing about the installation: the JVM CLI can take
  # over 3 seconds while the harness is starting its MCP servers. Reporting it told agents the
  # render tools might be broken when they worked, and they skipped rendering (#86). Only
  # failures that someone can act on reach the session context.
  :
elif [ "$help_status" -ne 0 ]; then
  append_context "The MCP capability probe failed."
elif grep -Eq '(^|[[:space:]])doctor([[:space:]]|$)' "$help_output"; then
  doctor_output="$temporary_root/doctor.out"
  if run_probe "$doctor_output" "$temporary_root/doctor.timed-out" compose-preview mcp doctor --json; then
    doctor_status=0
  else
    doctor_status=$?
  fi
  if [ "$doctor_status" -eq 124 ]; then
    :
  elif [ "$doctor_status" -ne 0 ]; then
    append_context "MCP doctor failed."
  fi
fi

design_help_output="$temporary_root/design-help.out"
if run_probe "$design_help_output" "$temporary_root/design-help.timed-out" compose-preview design --help; then
  design_help_status=0
else
  design_help_status=$?
fi
if [ "$design_help_status" -eq 124 ]; then
  # The first `design` call on a machine without a cached server distribution downloads one and
  # outlasts the probe. That is not something to act on, and the next session finds it cached.
  :
elif [ "$design_help_status" -ne 0 ]; then
  # Older launchers predate the top-level `design` command. A successful root help that does not
  # advertise it is an unsupported capability, not a broken installation and not session context.
  root_help_output="$temporary_root/root-help.out"
  if run_probe "$root_help_output" "$temporary_root/root-help.timed-out" compose-preview --help; then
    root_help_status=0
  else
    root_help_status=$?
  fi
  if [ "$root_help_status" -eq 124 ]; then
    :
  elif [ "$root_help_status" -ne 0 ] || grep -Eq '(^|[[:space:]])design([[:space:]]|$)' "$root_help_output"; then
    append_context "The design-status capability probe failed."
  fi
elif grep -Eq '(^|[[:space:]])status([[:space:]]|$)' "$design_help_output"; then
  status_output="$temporary_root/status.out"
  if run_probe "$status_output" "$temporary_root/status.timed-out" \
    compose-preview design status --workspace "$workspace_root" --json --timeout 2; then
    status_status=0
  else
    status_status=$?
  fi
  if [ "$status_status" -eq 124 ]; then
    :
  elif [ "$status_status" -ne 0 ]; then
    append_context "Workspace design status failed."
  elif [ -s "$status_output" ]; then
    if status_summary_text=$(status_summary "$status_output"); then
      if [ -n "$status_summary_text" ]; then
        append_context "$status_summary_text"
      fi
    else
      append_context "Workspace design status returned an unreadable summary."
    fi
  fi
fi

# One fixed routing line for a Gradle workspace. In the evals the skills were often not loaded for a
# plain render request, and the agent searched the project before rendering (T5) or wrote preview
# files to show a library component (H6). A hook is always seen, so the render-first rule rides here.
routing_hint=
if [ -f "$workspace_root/settings.gradle.kts" ] || [ -f "$workspace_root/settings.gradle" ]; then
  routing_hint="Compose Preview: to see a composable or @Preview, call render_preview with preview=<FunctionName> first; don't search the project before it, since a miss lists the closest matches. Library components (Material 3, Wear) come from the hosted catalog's catalog_* tools, not from new preview files in this project."
fi

if [ -n "$context_message" ]; then
  emit_context "Compose Preview needs attention: $context_message${routing_hint:+ $routing_hint}"
elif [ -n "$routing_hint" ]; then
  emit_context "$routing_hint"
fi
