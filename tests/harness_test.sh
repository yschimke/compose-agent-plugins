#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
# shellcheck source=../plugins/compose-preview/scripts/lib/harness.sh
. "$repository_root/plugins/compose-preview/scripts/lib/harness.sh"

failures=0

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  failures=$((failures + 1))
}

assert_equal() {
  if [ "$1" != "$2" ]; then
    fail "$3 (expected: $1; actual: $2)"
  fi
}

assert_status() {
  expected_status=$1
  actual_status=$2
  description=$3
  if [ "$expected_status" -ne "$actual_status" ]; then
    fail "$description (expected status: $expected_status; actual: $actual_status)"
  fi
}

assert_json_continue() {
  expected_decision=$1
  reason=$2
  description=$3
  output=$(harness_emit_continue "$reason")
  if ! printf '%s\n' "$output" | python3 -c '
import json
import sys

actual = json.load(sys.stdin)
expected = {"decision": sys.argv[1], "reason": sys.argv[2]}
if actual != expected:
    raise SystemExit(f"expected {expected!r}, got {actual!r}")
' "$expected_decision" "$reason"; then
    fail "$description must be valid JSON with an unchanged reason"
  fi
}

clear_harness_environment() {
  unset CLAUDECODE CLAUDE_PLUGIN_ROOT CODEX_THREAD_ID __CFBundleIdentifier ANTIGRAVITY_CLI_ALIAS OPENCODE GEMINI_CLI HARNESS
}

check_detection() {
  expected_harness=$1
  shift
  clear_harness_environment
  "$@"
  harness_detect
  assert_equal "$expected_harness" "$HARNESS" "detect $expected_harness"
}

set_claude() { CLAUDECODE=1; export CLAUDECODE; }
set_claude_plugin() { CLAUDE_PLUGIN_ROOT=/tmp/compose-preview; export CLAUDE_PLUGIN_ROOT; }
set_codex() { CODEX_THREAD_ID=thread-1; export CODEX_THREAD_ID; }
set_antigravity_bundle() { __CFBundleIdentifier=com.google.antigravity; export __CFBundleIdentifier; }
set_antigravity_alias() { ANTIGRAVITY_CLI_ALIAS=agy; export ANTIGRAVITY_CLI_ALIAS; }
set_opencode() { OPENCODE=1; export OPENCODE; }
set_gemini() { GEMINI_CLI=1; export GEMINI_CLI; }
set_nothing() { :; }

check_detection claude set_claude
check_detection claude set_claude_plugin
check_detection codex set_codex
check_detection antigravity set_antigravity_bundle
check_detection antigravity set_antigravity_alias
check_detection opencode set_opencode
check_detection gemini set_gemini
check_detection unknown set_nothing

# Codex exports CLAUDE_PLUGIN_ROOT to plugin hooks too; its thread id wins.
clear_harness_environment
set_codex
set_claude_plugin
harness_detect
assert_equal codex "$HARNESS" 'Codex plugin hook environment detects Codex'

clear_harness_environment
CODEX_THREAD_ID=thread-1
export CODEX_THREAD_ID
harness_detect --harness=antigravity
assert_equal antigravity "$HARNESS" 'explicit harness overrides environment'

if harness_detect --harness=unsupported >/dev/null 2>&1; then
  fail 'unsupported explicit harness must fail'
else
  assert_status 2 "$?" 'unsupported explicit harness status'
fi

if harness_detect --harness= >/dev/null 2>&1; then
  fail 'empty explicit harness must fail'
else
  assert_status 2 "$?" 'empty explicit harness status'
fi

harness_detect --harness=claude
claude_output=$(harness_emit_continue 'continue "carefully" \\ now')
assert_equal '{"decision":"block","reason":"continue \"carefully\" \\\\ now"}' "$claude_output" 'Claude output contract'

harness_detect --harness=antigravity
antigravity_output=$(harness_emit_continue 'continue "carefully" \\ now')
assert_equal '{"decision":"continue","reason":"continue \"carefully\" \\\\ now"}' "$antigravity_output" 'Antigravity output contract'

harness_detect --harness=codex
codex_output=$(harness_emit_continue 'continue "carefully" \\ now')
assert_equal '{"decision":"block","reason":"continue \"carefully\" \\\\ now"}' "$codex_output" 'Codex output contract'

for notice_harness in claude codex; do
  harness_detect --harness="$notice_harness"
  notice_output=$(harness_emit_notice 'remember "this"')
  assert_equal '{"systemMessage":"remember \"this\""}' "$notice_output" "$notice_harness notice contract"
done

for no_notice_harness in antigravity opencode gemini unknown; do
  harness_detect --harness="$no_notice_harness"
  if notice_output=$(harness_emit_notice 'remember' 2>/dev/null); then
    fail "$no_notice_harness must not emit a notice"
  else
    assert_status 2 "$?" "$no_notice_harness notice status"
  fi
  assert_equal '' "$notice_output" "$no_notice_harness notice output"
done

for session_harness in claude codex unknown; do
  harness_detect --harness="$session_harness"
  session_output=$(harness_emit_session_start 'start "here"')
  assert_equal '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"start \"here\""}}' "$session_output" "$session_harness session-start contract"
done

harness_detect --harness=antigravity
agy_session_output=$(harness_emit_session_start 'start "here"')
assert_equal '{"injectSteps":[{"systemMessage":{"systemMessage":"start \"here\""}}]}' "$agy_session_output" 'antigravity session-start contract'

for no_session_harness in opencode gemini; do
  harness_detect --harness="$no_session_harness"
  if session_output=$(harness_emit_session_start 'start' 2>/dev/null); then
    fail "$no_session_harness must not emit a session-start payload"
  else
    assert_status 2 "$?" "$no_session_harness session-start status"
  fi
  assert_equal '' "$session_output" "$no_session_harness session-start output"
done

for continue_harness in claude codex antigravity; do
  harness_detect --harness="$continue_harness"
  case "$continue_harness" in
    claude|codex) expected_decision=block ;;
    antigravity) expected_decision=continue ;;
  esac
  assert_json_continue "$expected_decision" 'a\b' "$continue_harness escapes one backslash"
  assert_json_continue "$expected_decision" 'C:\path' "$continue_harness escapes a path"
  assert_json_continue "$expected_decision" 'say "hi"' "$continue_harness escapes quotes"
  assert_json_continue "$expected_decision" 'two\\x' "$continue_harness escapes consecutive backslashes"
  assert_json_continue "$expected_decision" 'mix "q" \ end' "$continue_harness escapes mixed punctuation"
done

for no_stop_harness in opencode gemini unknown; do
  harness_detect --harness="$no_stop_harness"
  if harness_emit_continue 'not supported' >/dev/null 2>&1; then
    fail "$no_stop_harness must not emit a Stop-hook response"
  else
    assert_status 2 "$?" "$no_stop_harness non-target status"
  fi
done

if [ "$failures" -ne 0 ]; then
  exit 1
fi

printf '%s\n' 'harness tests passed'
