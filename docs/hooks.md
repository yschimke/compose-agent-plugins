# Hooks

What the `compose-preview` plugin's hooks do in each harness. The `compose-catalogs` plugin has
no hooks.

## Compose edit reminder

After the agent edits a `*.kt` file that declares a `@Composable` or `@Preview`,
the `compose-preview` plugin's PostToolUse hook adds one line of context: render
an affected preview with `render_preview` and look at it before calling the
change done (agent rule R1). A hook is always seen; a skill is not, and in
the eval run on #64 agents edited Compose UI without rendering even with the
skill offered (#86).

It reminds once per file per session, never blocks, and stays silent when the
edit touched no Compose file or when anything about the hook itself fails. It
runs in Claude Code (`Edit`, `Write`, `MultiEdit`) and Codex (`apply_patch`).
In OpenCode the same reminder is a plugin, `opencode/plugins/compose-preview.js`,
that appends the line to the `edit`, `write` or `apply_patch` result.
Antigravity gets only Stop hooks for now: its post-edit tool names differ and
its context output for that event has not been verified. Instead the
`compose-preview` plugin ships `rules/AGENTS.md`, which Antigravity loads on
every turn: render first with `project=<workspace>`, render after editing
Compose UI, and check `compose-preview design status` before finishing design
work. Claude Code ignores a plugin's `rules/`.

In a Gradle workspace, the SessionStart hook in Claude Code and Codex also adds
one routing line: call `render_preview` by name before searching the project,
and take library components from the hosted catalog rather than writing preview
files. It targets the grep-before-render and catalog-routing failures in the
evals on #64 (T5, H6).

When the CLI is installed in `~/.local/bin` but that directory is not on PATH
yet (a fresh sandbox shell), the same hook puts it there: in Claude Code it
adds one quoted `PATH` line to `$CLAUDE_ENV_FILE`, which reaches Bash calls.
The hook cannot change the PATH Claude Code starts MCP servers with, so the
plugin's `.mcp.json` launches the CLI through `sh`, appending `~/.local/bin`
to PATH; a `compose-preview` already on PATH still wins. The installer itself
writes no agent configuration.

## Compose Preview Stop gate

The `compose-preview` plugin's Stop hook does nothing unless
`COMPOSE_PREVIEW_GATE=1` is set in the environment the harness starts hooks
with. When it is set, the hook looks at previews declared in `*.kt` files that
differ from `HEAD` or are untracked. It runs `compose-preview show --json` and
`compose-preview a11y --json --fail-on errors`. It keeps the agent working
only when one of those previews:

- fails to render; or
- has accessibility errors. Warnings do not count.

It never blocks on image, hash or pixel changes, because a migration is
expected to change pixels (#10).

The gate lets the agent stop in these cases:

- a Stop hook already continued this turn (`stop_hook_active`);
- two turns in a row were already blocked in this session;
- `compose-preview`, `git` or `python3` is missing;
- the CLI fails, times out, or prints output the gate cannot parse.

Each CLI call is bounded by `COMPOSE_PREVIEW_GATE_TIMEOUT` seconds (default
150). A Gradle build that fails before it reports any previews counts as a tool
error, not a render failure.

When `ui-builder/designs/index.json` exists, the gate also asks
`compose-preview design status` about unacknowledged design comments (R4) and
unsaved temporary copies (R3). It reports them to the person but never blocks
because of them.

Each harness gets its own generated hook manifest, and every command passes
its harness explicitly:

- Claude Code (`hooks/hooks.json`, `--harness=claude`) and Codex
  (`hooks/codex-hooks.json`, `--harness=codex`) use the
  `{"decision":"block","reason":…}` response.
- Antigravity (the root `hooks.json`, `--harness=antigravity`) runs plugin-relative
  `./scripts/session-start-summary.sh --harness=antigravity` on `SessionStart`
  (emitting `injectSteps` when setup or design status needs attention) and
  `./scripts/stop-gate.sh --harness=antigravity` on `Stop` (emitting
  `{"decision":"continue","reason":…}`). Its Stop gate ignores non-normal
  `terminationReason` values (`USER_CANCELED`, `ERROR`, `MAX_INVOCATIONS`, etc.)
  and keys its two-turn consecutive-block cap by `conversationId`. The gate
  finds the checkout from the first `workspacePaths` entry. Antigravity has no
  non-blocking Stop message, so the design reminder is emitted on `SessionStart`
  rather than `Stop`.
