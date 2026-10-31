#!/bin/sh
# Opt-in compose-preview Stop gate (issues #4, #10 T4 and #12).
#
# Does nothing unless COMPOSE_PREVIEW_GATE=1. When enabled, it keeps the agent
# working only when a preview declared in a Kotlin file changed in the working
# tree fails to render, or has accessibility errors. It never blocks on image,
# hash or pixel changes: a migration is expected to change pixels (#10).
#
# Loop guard: it never blocks when the harness says a Stop hook already kept
# this turn going (stop_hook_active), and it allows the stop without checking
# after two consecutive blocked turns in one session. Antigravity sends no
# stop_hook_active and applies no cap of its own, so there the per-session
# count, keyed by its conversationId, is the only guard.
#
# Every failure of the gate itself allows the stop: a missing CLI, git or
# python3, a timeout, a non-zero exit it does not recognise, or output it
# cannot parse. Each CLI probe is bounded by COMPOSE_PREVIEW_GATE_TIMEOUT
# seconds (default 150).
#
# It also reminds, without blocking, about unsaved temporary design copies (R3)
# and unacknowledged design comments (R4) that `compose-preview design status`
# reports for this workspace.

[ "${COMPOSE_PREVIEW_GATE-}" = "1" ] || exit 0

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 0
# shellcheck source=lib/harness.sh
. "$script_dir/lib/harness.sh" || exit 0
harness_detect "$@" 2>/dev/null || exit 0
case "$HARNESS" in
  claude|codex|antigravity) ;;
  *) exit 0 ;;
esac

probe_timeout=${COMPOSE_PREVIEW_GATE_TIMEOUT:-150}
case "$probe_timeout" in
  ''|*[!0-9]*) probe_timeout=150 ;;
esac
[ "$probe_timeout" -gt 0 ] || probe_timeout=150
max_consecutive_blocks=2

temporary_root=$(mktemp -d "${TMPDIR:-/tmp}/compose-preview-stop-gate.XXXXXX") || exit 0
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
trap 'cleanup; exit 0' HUP INT TERM

# run_bounded <seconds> <stdout-file> <command...>
# Runs a command with closed stdin (asynchronous lists read /dev/null) and
# returns its status, or 124 when it outlived the bound and was killed.
run_bounded() {
  bounded_seconds=$1
  bounded_output=$2
  shift 2
  bounded_marker="$bounded_output.timed-out"
  rm -f "$bounded_marker"
  "$@" >"$bounded_output" 2>/dev/null &
  probe_pid=$!
  bounded_ticks=0
  bounded_limit=$((bounded_seconds * 10))
  while kill -0 "$probe_pid" 2>/dev/null && [ "$bounded_ticks" -lt "$bounded_limit" ]; do
    sleep 0.1
    bounded_ticks=$((bounded_ticks + 1))
  done
  if kill -0 "$probe_pid" 2>/dev/null; then
    : >"$bounded_marker"
    kill "$probe_pid" 2>/dev/null || true
    bounded_grace=0
    while kill -0 "$probe_pid" 2>/dev/null && [ "$bounded_grace" -lt 5 ]; do
      sleep 0.1
      bounded_grace=$((bounded_grace + 1))
    done
    kill -KILL "$probe_pid" 2>/dev/null || true
  fi
  wait "$probe_pid" 2>/dev/null
  bounded_status=$?
  probe_pid=
  if [ -f "$bounded_marker" ]; then
    return 124
  fi
  return "$bounded_status"
}

# The harness writes one JSON object to stdin. Read it with a bound so a
# held-open stdin cannot stall the stop.
hook_input="$temporary_root/input.json"
exec 3<&0
run_bounded 2 "$hook_input" sh -c 'cat <&3' || : >"$hook_input"
exec 3<&-

if grep -Eq '"stop_hook_active"[[:space:]]*:[[:space:]]*true' "$hook_input"; then
  exit 0
fi

# json_string_field <key>: the first plain string value of <key> in the input.
json_string_field() {
  sed -n 's/.*"'"$1"'"[[:space:]]*:[[:space:]]*"\([^"\\]*\)".*/\1/p' "$hook_input" | head -n 1
}

# Antigravity sends terminationReason on Stop. Only block when the agent chose
# to stop normally (NO_TOOL_CALL); never block on USER_CANCELED, ERROR or a
# budget/invocation cap.
termination_reason=$(json_string_field terminationReason)
if [ -n "$termination_reason" ] && [ "$termination_reason" != "NO_TOOL_CALL" ]; then
  exit 0
fi

# Claude Code and Codex send session_id; Antigravity sends conversationId (and
# exports ANTIGRAVITY_CONVERSATION_ID to hooks).
session_id=$(json_string_field session_id)
[ -n "$session_id" ] || session_id=$(json_string_field conversationId)
[ -n "$session_id" ] || session_id=${ANTIGRAVITY_CONVERSATION_ID-}
case "$session_id" in
  ''|*[!A-Za-z0-9._:-]*) session_id=unknown-session ;;
esac
[ "${#session_id}" -le 128 ] || session_id=unknown-session
session_key=$(printf '%s' "$session_id" | tr -c 'A-Za-z0-9._-' '_')
state_root="${TMPDIR:-/tmp}/compose-preview-stop-gate-$(id -u 2>/dev/null || echo user)"
state_file="$state_root/$session_key.blocks"
consecutive_blocks=$(cat "$state_file" 2>/dev/null) || consecutive_blocks=0
case "$consecutive_blocks" in
  ''|*[!0-9]*) consecutive_blocks=0 ;;
esac

record_blocks() {
  mkdir -p "$state_root" 2>/dev/null && chmod 700 "$state_root" 2>/dev/null
  printf '%s\n' "$1" >"$state_file" 2>/dev/null || true
}

if [ "$consecutive_blocks" -ge "$max_consecutive_blocks" ]; then
  record_blocks 0
  exit 0
fi

# Work from the directory the harness reports, when it is a plain path.
# Antigravity sends no cwd; it lists workspacePaths, and the first one is used.
hook_cwd=$(json_string_field cwd)
if [ -z "$hook_cwd" ]; then
  hook_cwd=$(sed -n 's/.*"workspacePaths"[[:space:]]*:[[:space:]]*\[[[:space:]]*"\([^"\\]*\)".*/\1/p' "$hook_input" | head -n 1)
  hook_cwd=${hook_cwd#file://}
  if [ -n "$hook_cwd" ] && [ -d "$hook_cwd" ]; then
    cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/composeai"
    if mkdir -p "$cache_dir" 2>/dev/null; then
      printf '%s\n' "$hook_cwd" >"$cache_dir/antigravity-workspace" 2>/dev/null || true
    fi
  fi
fi
if [ -n "$hook_cwd" ] && [ -d "$hook_cwd" ]; then
  cd "$hook_cwd" 2>/dev/null || exit 0
fi

command -v compose-preview >/dev/null 2>&1 || exit 0
command -v git >/dev/null 2>&1 || exit 0
workspace_root=$(git rev-parse --show-toplevel 2>/dev/null </dev/null) || exit 0
cd "$workspace_root" 2>/dev/null || exit 0

block_reason=
reminder=

# --- Previews declared in Kotlin files changed in the working tree ---------

changed_files="$temporary_root/changed.txt"
{
  git diff --name-only HEAD -- </dev/null 2>/dev/null
  git ls-files --others --exclude-standard </dev/null 2>/dev/null
} | grep '\.kt$' | sort -u >"$changed_files"

if [ -s "$changed_files" ] && command -v python3 >/dev/null 2>&1; then
  show_output="$temporary_root/show.json"
  touched_ids="$temporary_root/touched.txt"
  failed_ids="$temporary_root/failed.txt"
  a11y_output="$temporary_root/a11y.json"
  : >"$touched_ids"
  : >"$failed_ids"

  run_bounded "$probe_timeout" "$show_output" compose-preview show --json
  show_status=$?
  # 0 is a clean render; 2 means a failed build or missing renders and still
  # prints JSON for what was discovered. Anything else is a gate error.
  case "$show_status" in
    0|2)
      if python3 - show "$show_output" "$changed_files" "$touched_ids" "$failed_ids" 2>/dev/null <<'PY'
import json
import sys

_, _, show_path, changed_path, touched_path, failed_path = sys.argv
with open(show_path, encoding="utf-8") as handle:
    data = json.load(handle)
if not isinstance(data, dict) or not isinstance(data.get("previews"), list):
    raise SystemExit(1)
if not str(data.get("schema", "")).startswith("compose-preview-show/"):
    raise SystemExit(1)
with open(changed_path, encoding="utf-8") as handle:
    changed = [line.strip() for line in handle if line.strip()]

def declared_in_changed_file(source):
    source = source.replace("\\", "/")
    return any(
        path == source or path.endswith("/" + source) or source.endswith("/" + path)
        for path in changed
    )

touched, failed = [], []
for preview in data["previews"]:
    if not isinstance(preview, dict):
        continue
    preview_id, source = preview.get("id"), preview.get("sourceFile")
    if not isinstance(preview_id, str) or not preview_id or "\n" in preview_id:
        continue
    if not isinstance(source, str) or not source or not declared_in_changed_file(source):
        continue
    touched.append(preview_id)
    params = preview.get("params") if isinstance(preview.get("params"), dict) else {}
    if params.get("kind") == "XR_SUBSPACE":
        continue  # Produces no PNG by design.
    captures = [c for c in preview.get("captures") or [] if isinstance(c, dict)]
    if captures:
        missing = any(c.get("pngPath") is None and not c.get("optional") for c in captures)
    else:
        missing = preview.get("pngPath") is None
    if missing:
        failed.append(preview_id)

with open(touched_path, "w", encoding="utf-8") as handle:
    handle.writelines(f"{preview_id}\n" for preview_id in touched)
with open(failed_path, "w", encoding="utf-8") as handle:
    handle.writelines(f"{preview_id}\n" for preview_id in failed)
PY
      then
        : >"$a11y_output"
        if [ -s "$touched_ids" ]; then
          if [ "$(wc -l <"$touched_ids" | tr -d ' ')" -eq 1 ]; then
            run_bounded "$probe_timeout" "$a11y_output" \
              compose-preview a11y --json --fail-on errors --id "$(head -n 1 "$touched_ids")"
          else
            run_bounded "$probe_timeout" "$a11y_output" compose-preview a11y --json --fail-on errors
          fi
          # 0 is clean and 2 is a tripped threshold (or a failed build); both
          # print JSON when findings exist. Anything else is not trusted.
          case $? in
            0|2) ;;
            *) : >"$a11y_output" ;;
          esac
        fi
        block_reason=$(python3 - summary "$touched_ids" "$failed_ids" "$a11y_output" 2>/dev/null <<'PY'
import json
import sys

_, _, touched_path, failed_path, a11y_path = sys.argv

def lines(path):
    with open(path, encoding="utf-8") as handle:
        return [line.rstrip("\n") for line in handle if line.strip()]

def clean(text, limit=100):
    text = " ".join(str(text).split()).encode("ascii", "replace").decode("ascii")
    return text if len(text) <= limit else text[: limit - 3] + "..."

touched = set(lines(touched_path))
failed = lines(failed_path)
a11y = []
try:
    with open(a11y_path, encoding="utf-8") as handle:
        data = json.load(handle)
    previews = data.get("previews") if isinstance(data, dict) else None
    if not str(data.get("schema", "")).startswith("compose-preview-show/"):
        previews = None
except (OSError, ValueError, AttributeError):
    previews = None
for preview in previews or []:
    if not isinstance(preview, dict) or preview.get("id") not in touched:
        continue
    extensions = preview.get("dataExtensions")
    entry = extensions.get("a11y") if isinstance(extensions, dict) else None
    payload = entry.get("payload") if isinstance(entry, dict) else None
    findings = payload.get("findings") if isinstance(payload, dict) else None
    errors = [
        finding
        for finding in findings or []
        if isinstance(finding, dict) and finding.get("level") == "ERROR"
    ]
    if errors:
        first = errors[0]
        detail = ": ".join(
            clean(first.get(key), 60) for key in ("type", "message") if first.get(key)
        )
        a11y.append((preview["id"], len(errors), detail))

parts = []
if failed:
    shown = ", ".join(clean(preview_id, 80) for preview_id in failed[:5])
    more = f" and {len(failed) - 5} more" if len(failed) > 5 else ""
    noun = "preview" if len(failed) == 1 else "previews"
    parts.append(f"{len(failed)} changed {noun} failed to render ({shown}{more})")
if a11y:
    total = sum(count for _, count, _ in a11y)
    noun = "error" if total == 1 else "errors"
    shown = "; ".join(
        f"{clean(preview_id, 80)}: {count} ({detail})" if detail else f"{clean(preview_id, 80)}: {count}"
        for preview_id, count, detail in a11y[:5]
    )
    more = f"; and {len(a11y) - 5} more previews" if len(a11y) > 5 else ""
    parts.append(f"{total} accessibility {noun} in changed previews ({shown}{more})")
if parts:
    print(
        "Compose Preview gate: "
        + "; ".join(parts)
        + ". Fix them, or tell the person why they are expected, before finishing."
        + " Image and pixel changes are not checked. Run `compose-preview show` and"
        + " `compose-preview a11y --fail-on errors` to see the details."
    )
PY
        ) || block_reason=
      fi
      ;;
  esac
fi

# --- R3/R4 reminder: design comments and temporary copies ------------------

if [ -f ui-builder/designs/index.json ]; then
  design_output="$temporary_root/design.txt"
  if run_bounded 20 "$design_output" \
    compose-preview design status --summary --workspace "$workspace_root" --timeout 15; then
    # The summary is one fixed sentence of "; "-separated parts. Only the counts
    # are read back, so nothing else from it reaches the harness.
    design_parts="$temporary_root/design-parts.txt"
    tr ';' '\n' <"$design_output" >"$design_parts"
    design_comments=$(sed -n 's/^ *\([0-9][0-9]*\) unacknowledged design comment.*/\1/p' "$design_parts" | head -n 1)
    design_copies=$(sed -n 's/^ *\([0-9][0-9]*\) unsaved temporary cop.*/\1/p' "$design_parts" | head -n 1)
    design_items=
    if [ -n "$design_comments" ]; then
      design_items="$design_comments unacknowledged design comment(s)"
    fi
    if [ -n "$design_copies" ]; then
      [ -z "$design_items" ] || design_items="$design_items and "
      design_items="${design_items}$design_copies unsaved temporary design copy(ies)"
    fi
    if [ -n "$design_items" ]; then
      reminder="Compose Preview reminder: this workspace has $design_items. Save or discard temporary copies at the design's home, and reply to comments there, before finishing (docs/agent-rules.md R3, R4). Run \`compose-preview design status\` for details."
    fi
  fi
fi

if [ -n "$block_reason" ]; then
  if [ -n "$reminder" ]; then
    block_reason="$block_reason $reminder"
  fi
  if harness_emit_continue "$block_reason" 2>/dev/null; then
    record_blocks $((consecutive_blocks + 1))
  fi
  exit 0
fi

record_blocks 0
if [ -n "$reminder" ]; then
  harness_emit_notice "$reminder" 2>/dev/null || true
fi
exit 0
