#!/bin/sh
# Shared harness selection for compose-preview hooks.
#
# Generated hook commands must pass --harness=<name>. Environment detection is
# only a compatibility fallback.
#
# Stop-hook output contracts:
# - Claude Code: {"decision":"block","reason":...} keeps the agent working.
# - Codex: the same shape. Checked against codex-rs/hooks
#   schema/generated/stop.command.output.schema.json (openai/codex 67a7096),
#   which also sends stop_hook_active on input. A live Codex turn has not yet
#   observed a block (issue #6 Q4).
# - Antigravity: {"decision":"continue","reason":...}, a capped nudge.

# Sets HARNESS to one of: antigravity, claude, codex, opencode, gemini, unknown.
# An explicit --harness=<name> takes precedence over environment detection.
# Returns 2 for an invalid argument or an unsupported explicit harness.
harness_detect() {
  HARNESS=
  harness_override=
  harness_override_seen=0

  for harness_argument in "$@"; do
    case "$harness_argument" in
      --harness=*)
        if [ "$harness_override_seen" -eq 1 ]; then
          printf '%s\n' 'harness: --harness may be passed only once' >&2
          return 2
        fi
        harness_override=${harness_argument#--harness=}
        harness_override_seen=1
        ;;
      *)
        printf 'harness: unknown argument: %s\n' "$harness_argument" >&2
        return 2
        ;;
    esac
  done

  if [ "$harness_override_seen" -eq 1 ]; then
    case "$harness_override" in
      antigravity|claude|codex|opencode|gemini|unknown)
        HARNESS=$harness_override
        return 0
        ;;
      *)
        printf 'harness: unsupported harness: %s\n' "$harness_override" >&2
        return 2
        ;;
    esac
  fi

  # Keep these ordered. CLAUDECODE=1 is Claude Code's own marker. Codex also
  # exports CLAUDE_PLUGIN_ROOT to plugin hooks for compatibility, so its thread
  # id must be checked before that shared variable.
  if [ "${CLAUDECODE-}" = "1" ]; then
    HARNESS=claude
  elif [ -n "${CODEX_THREAD_ID-}" ]; then
    HARNESS=codex
  elif [ -n "${CLAUDE_PLUGIN_ROOT-}" ]; then
    HARNESS=claude
  elif [ "${__CFBundleIdentifier-}" = "com.google.antigravity" ] || [ -n "${ANTIGRAVITY_CLI_ALIAS-}" ]; then
    HARNESS=antigravity
  elif [ "${OPENCODE-}" = "1" ]; then
    HARNESS=opencode
  elif [ "${GEMINI_CLI-}" = "1" ]; then
    HARNESS=gemini
  else
    HARNESS=unknown
  fi
}

# Escapes one printable reason for a JSON string. Returns 2 for an empty
# reason or one containing control characters, so the JSON is never malformed.
harness_json_string() {
  harness_text=${1-}
  if [ -z "$harness_text" ]; then
    printf '%s\n' 'harness: a message must be non-empty' >&2
    return 2
  fi
  case "$harness_text" in
    *[![:print:]]*)
      printf '%s\n' 'harness: reason must contain printable characters only' >&2
      return 2
      ;;
  esac
  printf '%s' "$harness_text" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

# Emits the harness's "keep going" Stop response to stdout.
#
# OpenCode and Gemini are detected but not Stop-hook targets. Unknown callers
# are likewise not allowed to proceed silently.
# Returns 2 for invalid input or a non-target harness.
harness_emit_continue() {
  if [ "$#" -ne 1 ] || [ -z "${1-}" ]; then
    printf '%s\n' 'harness: harness_emit_continue requires one non-empty reason' >&2
    return 2
  fi
  harness_json_reason=$(harness_json_string "$1") || return 2
  case "${HARNESS-}" in
    antigravity)
      printf '{"decision":"continue","reason":"%s"}\n' "$harness_json_reason"
      ;;
    claude|codex)
      printf '{"decision":"block","reason":"%s"}\n' "$harness_json_reason"
      ;;
    opencode|gemini)
      printf 'harness: %s is not a Stop-hook target\n' "$HARNESS" >&2
      return 2
      ;;
    *)
      printf '%s\n' 'harness: unknown harness has no Stop-hook output contract' >&2
      return 2
      ;;
  esac
}

# Emits a Stop response that shows a message to the person without keeping the
# agent working. Only Claude Code and Codex define one (systemMessage); every
# other harness gets no output and status 2, so a reminder can never block.
harness_emit_notice() {
  if [ "$#" -ne 1 ] || [ -z "${1-}" ]; then
    printf '%s\n' 'harness: harness_emit_notice requires one non-empty message' >&2
    return 2
  fi
  harness_json_message=$(harness_json_string "$1") || return 2
  case "${HARNESS-}" in
    claude|codex)
      printf '{"systemMessage":"%s"}\n' "$harness_json_message"
      ;;
    *)
      printf 'harness: %s has no non-blocking Stop message\n' "${HARNESS:-unknown}" >&2
      return 2
      ;;
  esac
}

# Emits the harness's SessionStart context payload to stdout.
#
# - Claude Code / Codex (and default no-arg invocations): hookSpecificOutput.additionalContext
# - Antigravity: injectSteps[].systemMessage.systemMessage
harness_emit_session_start() {
  if [ "$#" -ne 1 ] || [ -z "${1-}" ]; then
    printf '%s\n' 'harness: harness_emit_session_start requires one non-empty message' >&2
    return 2
  fi
  harness_json_message=$(harness_json_string "$1") || return 2
  case "${HARNESS:-unknown}" in
    antigravity)
      printf '{"injectSteps":[{"systemMessage":{"systemMessage":"%s"}}]}\n' "$harness_json_message"
      ;;
    claude|codex|unknown)
      printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$harness_json_message"
      ;;
    *)
      printf 'harness: %s is not a SessionStart-hook target\n' "$HARNESS" >&2
      return 2
      ;;
  esac
}
