#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
script="$repository_root/plugins/compose-preview/scripts/session-start-summary.sh"
temporary_root="$(mktemp -d)"
trap 'rm -rf "$temporary_root"' EXIT

assert_equal() {
  local expected=$1
  local actual=$2
  local description=$3
  if [[ "$expected" != "$actual" ]]; then
    printf 'FAIL: %s (expected: %s; actual: %s)\n' "$description" "$expected" "$actual" >&2
    exit 1
  fi
}

expected_output() {
  local message=$1
  printf '%s' "{\"hookSpecificOutput\":{\"hookEventName\":\"SessionStart\",\"additionalContext\":\"${message}\"}}"
}

missing_output="$(PATH="$temporary_root/missing:/usr/bin:/bin" "$script")"
assert_equal "$(expected_output 'Compose Preview needs setup: compose-preview is not available on PATH.')" "$missing_output" 'missing CLI guidance'

fake_bin="$temporary_root/bin"
mkdir "$fake_bin"
fake_cli="$fake_bin/compose-preview"

printf '%s\n' '#!/bin/sh' 'if [ "$1 $2" = "mcp --help" ] || [ "$1 $2" = "design --help" ]; then exit 0; fi' 'exit 1' >"$fake_cli"
chmod +x "$fake_cli"
unsupported_output="$(PATH="$fake_bin:$PATH" "$script")"
assert_equal '' "$unsupported_output" 'unsupported doctor is a silent no-op'

printf '%s\n' '#!/bin/sh' 'if [ "$1 $2" = "mcp --help" ]; then exit 23; fi' 'if [ "$1 $2" = "design --help" ]; then exit 0; fi' 'exit 0' >"$fake_cli"
chmod +x "$fake_cli"
failed_help_output="$(PATH="$fake_bin:$PATH" "$script")"
assert_equal "$(expected_output 'Compose Preview needs attention: The MCP capability probe failed.')" "$failed_help_output" 'failed help guidance'

printf '%s\n' '#!/bin/sh' 'if [ "$1 $2" = "mcp --help" ]; then echo doctor; exit 0; fi' 'if [ "$1 $2" = "design --help" ]; then exit 0; fi' 'exit 0' >"$fake_cli"
chmod +x "$fake_cli"
ok_output="$(PATH="$fake_bin:$PATH" "$script")"
assert_equal '' "$ok_output" 'healthy doctor is a silent no-op'

printf '%s\n' '#!/bin/sh' 'if [ "$1 $2" = "mcp --help" ]; then exit 0; fi' 'if [ "$1 $2" = "design --help" ]; then exit 23; fi' 'if [ "$1" = "--help" ]; then echo design; exit 0; fi' 'exit 0' >"$fake_cli"
chmod +x "$fake_cli"
failed_design_help_output="$(PATH="$fake_bin:$PATH" "$script")"
assert_equal "$(expected_output 'Compose Preview needs attention: The design-status capability probe failed.')" "$failed_design_help_output" 'failed design help guidance'

printf '%s\n' '#!/bin/sh' 'if [ "$1 $2" = "mcp --help" ]; then exit 0; fi' 'if [ "$1 $2" = "design --help" ]; then exit 23; fi' 'if [ "$1" = "--help" ]; then echo mcp; exit 0; fi' 'exit 1' >"$fake_cli"
chmod +x "$fake_cli"
old_cli_output="$(PATH="$fake_bin:$PATH" "$script")"
assert_equal '' "$old_cli_output" 'older CLI without design is a silent no-op'

printf '%s\n' '#!/bin/sh' 'if [ "$1 $2" = "mcp --help" ]; then echo doctor; exit 0; fi' 'if [ "$1 $2" = "design --help" ]; then exit 0; fi' 'printf "%s\\n" "COMPOSE_PREVIEW_TOKEN=must-not-leak" >&2' 'exit 1' >"$fake_cli"
failed_output="$(PATH="$fake_bin:$PATH" "$script")"
assert_equal "$(expected_output 'Compose Preview needs attention: MCP doctor failed.')" "$failed_output" 'failed doctor guidance'
if [[ "$failed_output" == *must-not-leak* ]]; then
  printf '%s\n' 'FAIL: doctor diagnostics must not leak into the SessionStart summary' >&2
  exit 1
fi

# The released status command contributes only integers read from its versioned JSON envelope.
status_args="$temporary_root/status-args"
printf '%s\n' \
  '#!/bin/sh' \
  'if [ "$1 $2" = "mcp --help" ]; then echo doctor; exit 0; fi' \
  'if [ "$1 $2" = "mcp doctor" ]; then exit 0; fi' \
  'if [ "$1 $2" = "design --help" ]; then echo status; exit 0; fi' \
  'if [ "$1 $2" = "design status" ]; then printf "%s\n" "$*" >"$STATUS_ARGS"; cat "$STATUS_JSON"; exit 0; fi' \
  'exit 1' >"$fake_cli"
chmod +x "$fake_cli"
status_json="$temporary_root/status.json"
# Envelope shape as printed by compose-preview-server v3.75.0 `design status --json`.
printf '%s\n' '{"schema":"compose-preview-design-status/v1","verdict":"unavailable","totals":{"workspaceDesigns":4,"serverLinked":3,"unsavedTemporaryCopies":1,"unacknowledgedComments":2,"unavailable":2},"designs":[{"designId":"a","file":"ui-builder/designs/a.json","state":"unsaved","unacknowledgedComments":2},{"designId":"b","file":"ui-builder/designs/b.json","state":"clean","unacknowledgedComments":0},{"designId":"c","file":"ui-builder/designs/c.json","state":"unavailable","code":"REMOTE_UNAVAILABLE"},{"designId":"d","file":"ui-builder/designs/d.json","state":"unavailable","code":"MISSING_HOME"}]}' >"$status_json"
status_output="$(STATUS_JSON="$status_json" STATUS_ARGS="$status_args" CLAUDE_PROJECT_DIR="$temporary_root/project with spaces" PATH="$fake_bin:$PATH" "$script")"
assert_equal "$(expected_output 'Compose Preview needs attention: 2 unacknowledged design comments; 1 unsaved temporary copy; design server not running.')" "$status_output" 'actionable workspace design status'
assert_equal "design status --workspace $temporary_root/project with spaces --json --timeout 2" "$(cat "$status_args")" 'status workspace and bound'

# Until designs record a home (compose-preview-server#1157) every repo-published design reports
# MISSING_HOME. That is not an actionable problem and must not produce a warning on every session.
printf '%s\n' '{"schema":"compose-preview-design-status/v1","verdict":"unavailable","totals":{"workspaceDesigns":2,"serverLinked":0,"unsavedTemporaryCopies":0,"unacknowledgedComments":0,"unavailable":2},"designs":[{"designId":"a","file":"ui-builder/designs/a.json","state":"unavailable","code":"MISSING_HOME"},{"designId":"b","file":"ui-builder/designs/b.json","state":"unavailable","code":"MISSING_HOME"}]}' >"$status_json"
missing_home_output="$(STATUS_JSON="$status_json" STATUS_ARGS="$status_args" PATH="$fake_bin:$PATH" "$script")"
assert_equal '' "$missing_home_output" 'designs without a recorded home are silent'

printf '%s\n' '{"schema":"compose-preview-design-status/v1","verdict":"unavailable","totals":{"workspaceDesigns":3,"serverLinked":2,"unsavedTemporaryCopies":0,"unacknowledgedComments":1,"unavailable":2},"designs":[{"designId":"a","file":"ui-builder/designs/a.json","state":"unavailable","code":"MISSING_HOME"},{"designId":"b","file":"ui-builder/designs/b.json","state":"unavailable","code":"AUTHORIZATION_REQUIRED"},{"designId":"c","file":"ui-builder/designs/c.json","state":"clean","unacknowledgedComments":1}]}' >"$status_json"
mixed_home_output="$(STATUS_JSON="$status_json" STATUS_ARGS="$status_args" PATH="$fake_bin:$PATH" "$script")"
assert_equal "$(expected_output 'Compose Preview needs attention: 1 unacknowledged design comment; design inventory unavailable for 1 workspace-linked design.')" "$mixed_home_output" 'missing homes are excluded from the unavailable count only'

# Server-homed designs while the local server is down collapse into one hint, with no count.
printf '%s\n' '{"schema":"compose-preview-design-status/v1","verdict":"unavailable","totals":{"workspaceDesigns":3,"serverLinked":3,"unsavedTemporaryCopies":0,"unacknowledgedComments":0,"unavailable":3},"designs":[{"designId":"a","file":"ui-builder/designs/a.json","state":"unavailable","code":"REMOTE_UNAVAILABLE"},{"designId":"b","file":"ui-builder/designs/b.json","state":"unavailable","code":"REMOTE_UNAVAILABLE"},{"designId":"c","file":"ui-builder/designs/c.json","state":"unavailable","code":"AUTHORIZATION_REQUIRED"}]}' >"$status_json"
remote_output="$(STATUS_JSON="$status_json" STATUS_ARGS="$status_args" PATH="$fake_bin:$PATH" "$script")"
assert_equal "$(expected_output 'Compose Preview needs attention: design inventory unavailable for 1 workspace-linked design; design server not running.')" "$remote_output" 'remote-unavailable designs collapse into one hint'

# A clean workspace is a silent no-op.
printf '%s\n' '{"schema":"compose-preview-design-status/v1","verdict":"ok","totals":{"workspaceDesigns":0,"serverLinked":0,"unsavedTemporaryCopies":0,"unacknowledgedComments":0,"unavailable":0},"designs":[]}' >"$status_json"
clean_status_output="$(STATUS_JSON="$status_json" STATUS_ARGS="$status_args" PATH="$fake_bin:$PATH" "$script")"
assert_equal '' "$clean_status_output" 'clean workspace status is silent'

# An envelope from another schema version is not guessed at.
printf '%s\n' '{"schema":"compose-preview-design-status/v2","totals":{"unsavedTemporaryCopies":0,"unacknowledgedComments":0,"unavailable":0}}' >"$status_json"
other_schema_output="$(STATUS_JSON="$status_json" STATUS_ARGS="$status_args" PATH="$fake_bin:$PATH" "$script")"
assert_equal "$(expected_output 'Compose Preview needs attention: Workspace design status returned an unreadable summary.')" "$other_schema_output" 'unknown status schema is not parsed'

# Even stdout is treated as untrusted: anything but the versioned envelope is replaced.
printf '%s\n' \
  '#!/bin/sh' \
  'if [ "$1 $2" = "mcp --help" ]; then exit 0; fi' \
  'if [ "$1 $2" = "design --help" ]; then echo status; exit 0; fi' \
  'if [ "$1 $2" = "design status" ]; then echo "COMPOSE_PREVIEW_TOKEN=must-not-leak"; exit 0; fi' \
  'exit 0' >"$fake_cli"
chmod +x "$fake_cli"
unsafe_status_output="$(PATH="$fake_bin:$PATH" "$script")"
assert_equal "$(expected_output 'Compose Preview needs attention: Workspace design status returned an unreadable summary.')" "$unsafe_status_output" 'unsafe status summary is replaced'
if [[ "$unsafe_status_output" == *must-not-leak* ]]; then
  printf '%s\n' 'FAIL: status stdout must not leak into the SessionStart summary' >&2
  exit 1
fi

# Status failures and diagnostics collapse to one fixed sentence.
printf '%s\n' \
  '#!/bin/sh' \
  'if [ "$1 $2" = "mcp --help" ]; then exit 0; fi' \
  'if [ "$1 $2" = "design --help" ]; then echo status; exit 0; fi' \
  'if [ "$1 $2" = "design status" ]; then echo "credential=must-not-leak" >&2; exit 19; fi' \
  'exit 0' >"$fake_cli"
chmod +x "$fake_cli"
failed_status_output="$(PATH="$fake_bin:$PATH" "$script")"
assert_equal "$(expected_output 'Compose Preview needs attention: Workspace design status failed.')" "$failed_status_output" 'failed status guidance'
if [[ "$failed_status_output" == *must-not-leak* ]]; then
  printf '%s\n' 'FAIL: status diagnostics must not leak into the SessionStart summary' >&2
  exit 1
fi

# Both probes must see EOF even if the hook itself inherits a held-open stdin.
printf '%s\n' \
  '#!/bin/sh' \
  'if read -r unexpected; then exit 97; fi' \
  'if [ "$1 $2" = "mcp --help" ]; then echo doctor; fi' \
  'if [ "$1 $2" = "design --help" ]; then exit 0; fi' \
  'exit 0' >"$fake_cli"
chmod +x "$fake_cli"
held_stdin="$temporary_root/held-stdin"
mkfifo "$held_stdin"
(
  exec 3>"$held_stdin"
  sleep 10
) &
writer_pid=$!
started_at=$(date +%s)
stdin_output="$(PATH="$fake_bin:$PATH" "$script" <"$held_stdin")"
elapsed=$(($(date +%s) - started_at))
kill "$writer_pid" 2>/dev/null || true
wait "$writer_pid" 2>/dev/null || true
assert_equal '' "$stdin_output" 'closed stdin is a silent healthy result'
if ((elapsed >= 3)); then
  printf 'FAIL: closed-stdin probe took %s seconds\n' "$elapsed" >&2
  exit 1
fi

# A capability probe that never exits must still return before the hook timeout.
printf '%s\n' \
  '#!/bin/sh' \
  'if [ "$1 $2" = "mcp --help" ]; then while :; do :; done; fi' \
  'exit 0' >"$fake_cli"
chmod +x "$fake_cli"
started_at=$(date +%s)
hung_help_output="$(PATH="$fake_bin:$PATH" "$script")"
elapsed=$(($(date +%s) - started_at))
assert_equal '' "$hung_help_output" 'help probe timeout is silent'
if ((elapsed < 2 || elapsed >= 8)); then
  printf 'FAIL: help timeout took %s seconds\n' "$elapsed" >&2
  exit 1
fi

# The first `design` call can download a server distribution and outlast the probe. That is silent.
printf '%s\n' \
  '#!/bin/sh' \
  'if [ "$1 $2" = "mcp --help" ]; then exit 0; fi' \
  'if [ "$1 $2" = "design --help" ]; then while :; do :; done; fi' \
  'exit 0' >"$fake_cli"
chmod +x "$fake_cli"
hung_design_help_output="$(PATH="$fake_bin:$PATH" "$script")"
assert_equal '' "$hung_design_help_output" 'design capability probe timeout is silent'

# The workspace status call has the same hard process bound as the existing doctor call, and its
# timeout is silent too.
printf '%s\n' \
  '#!/bin/sh' \
  'if [ "$1 $2" = "mcp --help" ]; then exit 0; fi' \
  'if [ "$1 $2" = "design --help" ]; then echo status; exit 0; fi' \
  'if [ "$1 $2" = "design status" ]; then while :; do :; done; fi' \
  'exit 0' >"$fake_cli"
chmod +x "$fake_cli"
started_at=$(date +%s)
hung_status_output="$(PATH="$fake_bin:$PATH" "$script")"
elapsed=$(($(date +%s) - started_at))
assert_equal '' "$hung_status_output" 'status timeout is silent'
if ((elapsed < 2 || elapsed >= 8)); then
  printf 'FAIL: status timeout took %s seconds\n' "$elapsed" >&2
  exit 1
fi

# Several individually bounded slow probes must still leave time for the hook to emit context
# before the manifest's 10-second deadline. Doctor fails, so there is context to emit; the
# status probe runs out of budget, which is silent.
printf '%s\n' \
  '#!/bin/sh' \
  'sleep 2' \
  'if [ "$1 $2" = "mcp --help" ]; then echo doctor; exit 0; fi' \
  'if [ "$1 $2" = "mcp doctor" ]; then exit 1; fi' \
  'if [ "$1 $2" = "design --help" ]; then echo status; exit 0; fi' \
  'if [ "$1 $2" = "design status" ]; then echo "{\"schema\":\"compose-preview-design-status/v1\",\"totals\":{\"unsavedTemporaryCopies\":0,\"unacknowledgedComments\":1,\"unavailable\":0}}"; exit 0; fi' \
  'exit 0' >"$fake_cli"
chmod +x "$fake_cli"
started_at=$(date +%s)
cumulative_output="$(PATH="$fake_bin:$PATH" "$script")"
elapsed=$(($(date +%s) - started_at))
assert_equal "$(expected_output 'Compose Preview needs attention: MCP doctor failed.')" "$cumulative_output" 'cumulative hook deadline guidance'
if ((elapsed < 6 || elapsed >= 10)); then
  printf 'FAIL: cumulative hook deadline took %s seconds\n' "$elapsed" >&2
  exit 1
fi

# A capability probe that ignores SIGTERM must be escalated to SIGKILL.
printf '%s\n' \
  '#!/bin/sh' \
  'trap "" TERM' \
  'if [ "$1 $2" = "mcp --help" ]; then while :; do :; done; fi' \
  'exit 0' >"$fake_cli"
chmod +x "$fake_cli"
started_at=$(date +%s)
stubborn_help_output="$(PATH="$fake_bin:$PATH" "$script")"
elapsed=$(($(date +%s) - started_at))
assert_equal '' "$stubborn_help_output" 'SIGTERM-ignoring help probe is killed silently'
if ((elapsed < 2 || elapsed >= 8)); then
  printf 'FAIL: SIGTERM-ignoring help timeout took %s seconds\n' "$elapsed" >&2
  exit 1
fi

# Doctor has its own bound rather than relying only on the outer hook timeout. A slow doctor is
# not a broken installation, so its timeout is silent (#86).
printf '%s\n' \
  '#!/bin/sh' \
  'if [ "$1 $2" = "mcp --help" ]; then echo doctor; exit 0; fi' \
  'if [ "$1 $2" = "design --help" ]; then exit 0; fi' \
  'while :; do :; done' >"$fake_cli"
chmod +x "$fake_cli"
started_at=$(date +%s)
hung_doctor_output="$(PATH="$fake_bin:$PATH" "$script")"
elapsed=$(($(date +%s) - started_at))
assert_equal '' "$hung_doctor_output" 'doctor timeout is silent'
if ((elapsed < 2 || elapsed >= 8)); then
  printf 'FAIL: doctor timeout took %s seconds\n' "$elapsed" >&2
  exit 1
fi

routing_hint="Compose Preview: to see a composable or @Preview, call render_preview with preview=<FunctionName> first; don't search the project before it, since a miss lists the closest matches. Library components (Material 3, Wear) come from the hosted catalog's catalog_* tools, not from new preview files in this project."
gradle_project="$temporary_root/gradle project"
mkdir -p "$gradle_project"
: >"$gradle_project/settings.gradle.kts"

printf '%s\n' '#!/bin/sh' 'if [ "$1 $2" = "mcp --help" ]; then echo doctor; exit 0; fi' 'if [ "$1 $2" = "design --help" ]; then exit 0; fi' 'exit 0' >"$fake_cli"
chmod +x "$fake_cli"
gradle_ok_output="$(CLAUDE_PROJECT_DIR="$gradle_project" PATH="$fake_bin:$PATH" "$script")"
assert_equal "$(expected_output "$routing_hint")" "$gradle_ok_output" 'a healthy Gradle workspace gets only the routing hint'
gradle_cwd_output="$(cd "$gradle_project" && PATH="$fake_bin:$PATH" "$script")"
assert_equal "$(expected_output "$routing_hint")" "$gradle_cwd_output" 'without CLAUDE_PROJECT_DIR the working directory is the workspace'

printf '%s\n' '#!/bin/sh' 'if [ "$1 $2" = "mcp --help" ]; then echo doctor; exit 0; fi' 'if [ "$1 $2" = "design --help" ]; then exit 0; fi' 'exit 1' >"$fake_cli"
gradle_failed_output="$(CLAUDE_PROJECT_DIR="$gradle_project" PATH="$fake_bin:$PATH" "$script")"
assert_equal "$(expected_output "Compose Preview needs attention: MCP doctor failed. $routing_hint")" "$gradle_failed_output" 'attention comes before the routing hint'

gradle_missing_output="$(CLAUDE_PROJECT_DIR="$gradle_project" PATH="$temporary_root/missing:/usr/bin:/bin" "$script")"
assert_equal "$(expected_output 'Compose Preview needs setup: compose-preview is not available on PATH.')" "$gradle_missing_output" 'no routing hint when the CLI is missing'

printf '%s\n' 'session start summary tests passed'
