#!/usr/bin/env bash
# Golden tests for the opt-in compose-preview Stop gate (#4, #9, #10 T4, #12).
# A fake `compose-preview` on PATH stands in for the CLI; nothing runs Gradle.
# UPDATE_GOLDEN=1 rewrites tests/golden/stop-gate/ from the current output.
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
gate="$repository_root/plugins/compose-preview/scripts/stop-gate.sh"
golden="$repository_root/tests/golden/stop-gate"
temporary_root="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "$temporary_root"' EXIT

failures=0
fail() {
  printf 'FAIL: %s\n' "$*" >&2
  failures=$((failures + 1))
}

# --- Fixture: a git checkout with one changed preview file ------------------

workspace="$temporary_root/workspace"
mkdir -p "$workspace/app/src/main/kotlin/com/example"
git -C "$workspace" init --quiet
git -C "$workspace" config user.email test@example.invalid
git -C "$workspace" config user.name 'Stop gate test'
printf '%s\n' 'fun Screen() {}' >"$workspace/app/src/main/kotlin/com/example/Screen.kt"
printf '%s\n' 'fun Other() {}' >"$workspace/app/src/main/kotlin/com/example/Other.kt"
git -C "$workspace" add .
git -C "$workspace" commit --quiet -m fixture
printf '%s\n' 'fun Screen() { /* edited */ }' >"$workspace/app/src/main/kotlin/com/example/Screen.kt"

clean_workspace="$temporary_root/clean-workspace"
cp -R "$workspace" "$clean_workspace"
git -C "$clean_workspace" checkout --quiet -- .

fake_bin="$temporary_root/bin"
mkdir "$fake_bin"
cat >"$fake_bin/compose-preview" <<'SH'
#!/bin/sh
printf '%s\n' "$*" >>"$FAKE_LOG"
case "$1" in
  show)
    if [ -n "${FAKE_HANG-}" ]; then exec sleep 30; fi
    cat "$FAKE_SHOW_JSON" 2>/dev/null
    exit "${FAKE_SHOW_STATUS:-0}"
    ;;
  a11y)
    cat "$FAKE_A11Y_JSON" 2>/dev/null
    exit "${FAKE_A11Y_STATUS:-0}"
    ;;
  design)
    cat "$FAKE_DESIGN" 2>/dev/null
    exit "${FAKE_DESIGN_STATUS:-0}"
    ;;
esac
exit 1
SH
chmod +x "$fake_bin/compose-preview"

data="$temporary_root/data"
mkdir "$data"

# One preview in the changed file, one in an untouched file. Both images
# changed since the last run: the gate must not care.
preview_json() {
  local screen_png=$1 screen_a11y=$2 other_a11y=$3
  cat <<JSON
{
  "schema": "compose-preview-show/v2",
  "previews": [
    {
      "id": "com.example.ScreenKt.ScreenPreview",
      "module": ":app",
      "functionName": "ScreenPreview",
      "className": "com.example.ScreenKt",
      "sourceFile": "com/example/Screen.kt",
      "params": {"kind": "COMPOSE"},
      "captures": [{"pngPath": $screen_png, "sha256": "bbbb", "changed": true}],
      "pngPath": $screen_png,
      "sha256": "bbbb",
      "changed": true,
      "dataExtensions": {$screen_a11y}
    },
    {
      "id": "com.example.OtherKt.OtherPreview",
      "module": ":app",
      "functionName": "OtherPreview",
      "className": "com.example.OtherKt",
      "sourceFile": "com/example/Other.kt",
      "params": {"kind": "COMPOSE"},
      "captures": [{"pngPath": "/renders/other.png", "sha256": "cccc", "changed": true}],
      "dataExtensions": {$other_a11y}
    }
  ],
  "counts": {"total": 2, "changed": 2, "unchanged": 0, "missing": 0, "skipped": 0}
}
JSON
}

a11y_extension() {
  local level=$1
  printf '"a11y": {"schema": "compose-preview-a11y/v1", "payload": {"previewId": "x", "findings": [{"level": "%s", "type": "TouchTargetSizeCheck", "message": "This item may be too small for touch targets."}]}}' "$level"
}

preview_json '"/renders/screen.png"' '' '' >"$data/show-pixels-changed.json"
preview_json 'null' '' '' >"$data/show-render-failed.json"
preview_json '"/renders/screen.png"' "$(a11y_extension ERROR)" '' >"$data/a11y-error.json"
preview_json '"/renders/screen.png"' "$(a11y_extension WARNING)" '' >"$data/a11y-warning.json"
preview_json '"/renders/screen.png"' '' "$(a11y_extension ERROR)" >"$data/a11y-error-untouched.json"
printf '%s\n' 'Gradle said something that is not JSON' >"$data/garbage.txt"
printf '%s\n' '2 unacknowledged design comments; 1 unsaved temporary copy.' >"$data/design-attention.txt"

# --- Runner -----------------------------------------------------------------

run_gate() {
  # run_gate <harness> <workspace> [stop_hook_active] ; env configures the fake.
  # Each call runs in a command-substitution subshell, so a fresh session id
  # comes from that subshell's pid unless SESSION_ID pins one.
  local harness=$1 cwd=$2 active=${3:-false}
  local subshell_pid=${BASHPID:-$(sh -c 'echo "$PPID"')}
  local session=${SESSION_ID:-session-$subshell_pid}
  printf '{"session_id":"%s","cwd":"%s","hook_event_name":"Stop","stop_hook_active":%s}' \
    "$session" "$cwd" "$active" |
    TMPDIR="$temporary_root/tmp" "$gate" --harness="$harness"
}
mkdir "$temporary_root/tmp"

run_antigravity_gate() {
  # run_antigravity_gate <workspace> <conversation> : the payload #6 Q4 recorded
  # for agy 1.2.12, with no cwd and no stop_hook_active. It runs from / so the
  # workspace can only come from workspacePaths.
  local cwd=$1 conversation=$2
  printf '{"artifactDirectoryPath":"/tmp/artifacts","conversationId":"%s","error":null,"executionNum":0,"fullyIdle":true,"modelName":"m","terminationReason":"NO_TOOL_CALL","transcriptPath":"/tmp/t.jsonl","workspacePaths":["%s"]}' \
    "$conversation" "$cwd" |
    (cd / && TMPDIR="$temporary_root/tmp" "$gate" --harness=antigravity)
}

log="$temporary_root/cli.log"
reset_fake() {
  : >"$log"
  export FAKE_LOG="$log"
  export FAKE_SHOW_JSON="$data/show-pixels-changed.json" FAKE_SHOW_STATUS=0
  export FAKE_A11Y_JSON="$data/show-pixels-changed.json" FAKE_A11Y_STATUS=0
  export FAKE_DESIGN=/dev/null FAKE_DESIGN_STATUS=0
  unset FAKE_HANG SESSION_ID COMPOSE_PREVIEW_GATE_TIMEOUT
  export COMPOSE_PREVIEW_GATE=1
  export PATH="$fake_bin:$base_path"
}
base_path=$PATH

expect_output() {
  local description=$1 expected=$2 actual=$3
  if [[ "$expected" != "$actual" ]]; then
    fail "$description"$'\n'"  expected: $expected"$'\n'"  actual:   $actual"
  fi
}

expect_golden() {
  local description=$1 name=$2 actual=$3
  if [[ "${UPDATE_GOLDEN-}" == 1 ]]; then
    mkdir -p "$golden"
    printf '%s\n' "$actual" >"$golden/$name"
  fi
  if [[ ! -f "$golden/$name" ]]; then
    fail "$description: missing golden file tests/golden/stop-gate/$name"
    return
  fi
  expect_output "$description ($name)" "$(cat "$golden/$name")" "$actual"
  if ! printf '%s' "$actual" | python3 -c 'import json, sys; json.load(sys.stdin)'; then
    fail "$description: output is not JSON"
  fi
}

expect_no_cli() {
  if [[ -s "$log" ]]; then
    fail "$1: the CLI must not run (ran: $(tr '\n' '|' <"$log"))"
  fi
}

# --- Cases ------------------------------------------------------------------

reset_fake
unset COMPOSE_PREVIEW_GATE
expect_output 'gate off allows the stop' '' "$(run_gate claude "$workspace")"
expect_no_cli 'gate off'
COMPOSE_PREVIEW_GATE=0
export COMPOSE_PREVIEW_GATE
expect_output 'COMPOSE_PREVIEW_GATE=0 allows the stop' '' "$(run_gate claude "$workspace")"
expect_no_cli 'COMPOSE_PREVIEW_GATE=0'

# #10 T4: a migration changes pixels, so image and hash changes never block.
for harness in claude codex antigravity; do
  reset_fake
  expect_output "$harness image and hash changes only allow the stop" '' \
    "$(run_gate "$harness" "$workspace")"
  grep -q '^show --json$' "$log" || fail "$harness: the gate must render the previews"
  grep -q '^a11y --json --fail-on errors --id com.example.ScreenKt.ScreenPreview$' "$log" ||
    fail "$harness: the gate must scope a11y to the one changed preview"
done

reset_fake
FAKE_A11Y_JSON="$data/a11y-warning.json"
expect_output 'accessibility warnings allow the stop' '' "$(run_gate claude "$workspace")"

reset_fake
FAKE_A11Y_JSON="$data/a11y-error-untouched.json" FAKE_A11Y_STATUS=2
expect_output 'errors in unchanged previews allow the stop' '' "$(run_gate claude "$workspace")"

for harness in claude codex antigravity; do
  reset_fake
  FAKE_SHOW_JSON="$data/show-render-failed.json" FAKE_SHOW_STATUS=2
  expect_golden "$harness render failure blocks" "render-failure.$harness.json" \
    "$(run_gate "$harness" "$workspace")"

  reset_fake
  FAKE_A11Y_JSON="$data/a11y-error.json" FAKE_A11Y_STATUS=2
  expect_golden "$harness accessibility error blocks" "a11y-error.$harness.json" \
    "$(run_gate "$harness" "$workspace")"
done

for harness in opencode gemini unknown bogus; do
  reset_fake
  FAKE_SHOW_JSON="$data/show-render-failed.json" FAKE_SHOW_STATUS=2
  expect_output "$harness is not a Stop target" '' "$(run_gate "$harness" "$workspace")"
done

reset_fake
FAKE_SHOW_JSON="$data/show-render-failed.json" FAKE_SHOW_STATUS=2
expect_output 'stop_hook_active allows the stop' '' "$(run_gate claude "$workspace" true)"
expect_no_cli 'stop_hook_active'

reset_fake
FAKE_SHOW_JSON="$data/show-render-failed.json" FAKE_SHOW_STATUS=2
SESSION_ID=looping-session
expect_golden 'first blocked turn' render-failure.claude.json "$(run_gate claude "$workspace")"
expect_golden 'second blocked turn' render-failure.claude.json "$(run_gate claude "$workspace")"
: >"$log"
expect_output 'third consecutive turn is allowed' '' "$(run_gate claude "$workspace")"
expect_no_cli 'after the consecutive-block cap'
expect_golden 'the cap resets after allowing' render-failure.claude.json "$(run_gate claude "$workspace")"

# Antigravity: workspacePaths locates the checkout, and conversationId keys the
# consecutive-block cap, which is its only loop guard.
reset_fake
expect_output 'Antigravity pixel changes allow the stop' '' \
  "$(run_antigravity_gate "$workspace" conversation-pixels)"
grep -q '^show --json$' "$log" || fail 'Antigravity: workspacePaths must locate the checkout'

reset_fake
FAKE_SHOW_JSON="$data/show-render-failed.json" FAKE_SHOW_STATUS=2
expect_golden 'Antigravity payload first block' render-failure.antigravity.json \
  "$(run_antigravity_gate "$workspace" conversation-a)"
expect_golden 'Antigravity payload second block' render-failure.antigravity.json \
  "$(run_antigravity_gate "$workspace" conversation-a)"
expect_golden 'another Antigravity conversation has its own cap' render-failure.antigravity.json \
  "$(run_antigravity_gate "$workspace" conversation-b)"
: >"$log"
expect_output 'third Antigravity block in one conversation is allowed' '' \
  "$(run_antigravity_gate "$workspace" conversation-a)"
expect_no_cli 'after the Antigravity consecutive-block cap'
expect_golden 'the Antigravity cap resets after allowing' render-failure.antigravity.json \
  "$(run_antigravity_gate "$workspace" conversation-a)"

reset_fake
FAKE_SHOW_JSON="$data/show-render-failed.json" FAKE_SHOW_STATUS=2
expect_golden 'file:// workspacePaths are accepted' render-failure.antigravity.json \
  "$(run_antigravity_gate "file://$workspace" conversation-file-url)"

for non_normal_reason in USER_CANCELED ERROR MAX_INVOCATIONS; do
  reset_fake
  FAKE_SHOW_JSON="$data/show-render-failed.json" FAKE_SHOW_STATUS=2
  actual_reason_out=$(
    printf '{"conversationId":"conv-%s","terminationReason":"%s","workspacePaths":["%s"]}' \
      "$non_normal_reason" "$non_normal_reason" "$workspace" |
      (cd / && TMPDIR="$temporary_root/tmp" "$gate" --harness=antigravity)
  )
  expect_output "Antigravity terminationReason=$non_normal_reason allows the stop" '' "$actual_reason_out"
  expect_no_cli "Antigravity terminationReason=$non_normal_reason"
done

reset_fake
expect_output 'no changed Kotlin allows the stop' '' "$(run_gate claude "$clean_workspace")"
if grep -q '^show' "$log"; then fail 'no changed Kotlin must not render'; fi

reset_fake
PATH="$temporary_root/no-cli:$base_path"
expect_output 'missing CLI allows the stop' '' "$(run_gate claude "$workspace")"

reset_fake
FAKE_SHOW_STATUS=1
FAKE_SHOW_JSON="$data/show-render-failed.json"
expect_output 'CLI error status allows the stop' '' "$(run_gate claude "$workspace")"

reset_fake
FAKE_SHOW_JSON="$data/garbage.txt" FAKE_SHOW_STATUS=2
expect_output 'unparseable render output allows the stop' '' "$(run_gate claude "$workspace")"

reset_fake
FAKE_A11Y_JSON="$data/garbage.txt" FAKE_A11Y_STATUS=2
expect_output 'unparseable a11y output allows the stop' '' "$(run_gate claude "$workspace")"

reset_fake
FAKE_A11Y_JSON="$data/a11y-error.json" FAKE_A11Y_STATUS=1
expect_output 'a11y tool error allows the stop' '' "$(run_gate claude "$workspace")"

reset_fake
export FAKE_HANG=1 COMPOSE_PREVIEW_GATE_TIMEOUT=1
started_at=$(date +%s)
expect_output 'a hung CLI allows the stop' '' "$(run_gate claude "$workspace")"
elapsed=$(($(date +%s) - started_at))
if ((elapsed >= 6)); then fail "timeout took $elapsed seconds"; fi

# Without python3 the preview checks cannot parse anything, so they are skipped.
no_python="$temporary_root/no-python"
mkdir "$no_python"
for tool in sh cat git grep sed sort tr wc head mkdir mktemp rm chmod id sleep dirname; do
  ln -s "$(command -v "$tool")" "$no_python/$tool"
done
reset_fake
FAKE_SHOW_JSON="$data/show-render-failed.json" FAKE_SHOW_STATUS=2
PATH="$fake_bin:$no_python"
expect_output 'missing python3 allows the stop' '' "$(run_gate claude "$workspace")"
# Control: the same minimal PATH plus python3 blocks, so the case above tested
# python3 and not some other missing tool.
with_python="$temporary_root/with-python"
PATH="$base_path" mkdir "$with_python"
PATH="$base_path" ln -s "$(PATH="$base_path" command -v python3)" "$with_python/python3"
PATH="$fake_bin:$no_python:$with_python"
expect_golden 'minimal PATH with python3 blocks' render-failure.claude.json \
  "$(run_gate claude "$workspace")"
PATH="$fake_bin:$base_path"

# R3/R4 reminders: shown, never blocking, and only with a design index.
mkdir -p "$workspace/ui-builder/designs" "$clean_workspace/ui-builder/designs"
printf '%s\n' '{}' >"$workspace/ui-builder/designs/index.json"
printf '%s\n' '{}' >"$clean_workspace/ui-builder/designs/index.json"
for harness in claude codex; do
  reset_fake
  FAKE_DESIGN="$data/design-attention.txt"
  expect_golden "$harness design reminder" "design-reminder.$harness.json" \
    "$(run_gate "$harness" "$clean_workspace")"
done
reset_fake
FAKE_DESIGN="$data/design-attention.txt"
expect_output 'Antigravity reminders never nudge' '' "$(run_gate antigravity "$clean_workspace")"
grep -q "^design status --summary --workspace $clean_workspace --timeout 15\$" "$log" ||
  fail 'design status must be asked for its summary of this workspace'

reset_fake
FAKE_DESIGN="$data/design-attention.txt"
FAKE_SHOW_JSON="$data/show-render-failed.json" FAKE_SHOW_STATUS=2
expect_golden 'a block carries the design reminder' render-failure-with-reminder.claude.json \
  "$(run_gate claude "$workspace")"

reset_fake
FAKE_DESIGN="$data/garbage.txt"
expect_output 'unrecognised design status is ignored' '' "$(run_gate claude "$clean_workspace")"

reset_fake
FAKE_DESIGN="$data/design-attention.txt" FAKE_DESIGN_STATUS=1
expect_output 'failed design status is ignored' '' "$(run_gate claude "$clean_workspace")"

rm -rf "$workspace/ui-builder" "$clean_workspace/ui-builder"
reset_fake
FAKE_DESIGN="$data/design-attention.txt"
expect_output 'no design index skips design status' '' "$(run_gate claude "$clean_workspace")"
expect_no_cli 'no design index and no changed Kotlin'

if ((failures)); then
  exit 1
fi
printf '%s\n' 'stop gate tests passed'
