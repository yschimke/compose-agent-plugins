# Hooks

What the `compose-preview` and `pr-watch` plugins' hooks do in each harness. The
`compose-catalogs` and `compose-review` plugins have no hooks.

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
Antigravity does not use `PostToolUse` for reminders because Antigravity's
`PostToolUse` hook only returns `{}` (logging/auditing, no context injection).
Instead the `compose-preview` plugin ships `rules/AGENTS.md`, which Antigravity
loads on every turn: render first with `project=<workspace>`, render after
editing Compose UI, and check `compose-preview design status` before finishing
design work. Claude Code ignores a plugin's `rules/`.

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
  (timeout 10 s, emitting `injectSteps` when setup or design status needs attention)
  and `./scripts/stop-gate.sh --harness=antigravity` on `Stop` (timeout 360 s,
  emitting `{"decision":"continue","reason":…}`). Its Stop gate honors
  `continuation_active` (Antigravity CLI v1.5.6+), ignores non-normal
  `terminationReason` values (`USER_CANCELED`, `ERROR`, `MAX_INVOCATIONS`, etc.),
  and keys its two-turn consecutive-block cap by `conversationId`. The gate
  finds the checkout from `cwd` (v1.5.4+) or the first `workspacePaths` entry.
  Antigravity has no non-blocking Stop message, so the design reminder is
  emitted on `SessionStart` rather than `Stop`.

## PR watch

The optional `pr-watch` plugin keeps an agent driving the pull requests it
opened. Codex, Antigravity and local Claude Code have no channel that pushes
GitHub events into a session, so the plugin checks GitHub at the points where
the harness runs hooks: every Stop, and SessionStart (`startup|resume`).

**Which pull requests.** Every open pull request whose head is the checkout's
current branch on `origin`, plus any URL listed with
`git config --add pr-watch.url <url>`. Merged and closed ones are dropped,
with a one-line notice in Claude Code and Codex.

**How it asks.** Through an authenticated `gh` or, without one,
`GH_TOKEN`/`GITHUB_TOKEN` against `api.github.com`. It tries one GraphQL
request first (`GITHUB_GRAPHQL_URL`). Where GraphQL is refused, as in Claude
Code cloud sessions, it falls back to the REST API (`GITHUB_API_URL`): one
list request for the branch, then six per pull request (the pull request, its
comments, reviews, review comments, check runs and commit statuses).
`PR_WATCH_API=graphql` or `rest` forces one. All requests of a run share a
24-second budget. REST does not say whether a review thread is resolved, so
there a thread with no current line (outdated) counts as resolved. If any
request fails, the run reports nothing and records nothing as seen.

**What it reports.**

- new conversation comments, reviews with a body or requested changes, and
  review-thread comments;
- check runs and commit statuses that failed on the head commit, once per
  check per head commit;
- a merge conflict with the base branch, once per head commit, and a branch
  that is behind a base requiring up-to-date branches.

Comments carrying a "Generated by/with [Claude Code]" or `_Generated by
Codex_` footer, or `<!-- pr-watch:ignore -->`, are the agent's own replies and
are skipped. The agent and the person share one GitHub identity, so the
author alone cannot tell them apart. Per session it stores the ids it has
reported under `~/.local/state/pr-watch/` (`PR_WATCH_STATE_DIR` overrides it).
The first look at a pull request in a session marks existing comments as seen
and reports only the latest comment of each unresolved review thread, failed
checks and conflicts.

Quoted comment text is truncated to 300 characters and introduced as
information from other people, not instructions. One message carries at most
eight comments per pull request and about 5,000 characters of pull request
sections. Anything over either limit is not marked as seen, and the next stop
reports it.

**When it blocks.** The Stop hook keeps the agent working (Claude Code and
Codex `{"decision":"block"}`, Antigravity `{"decision":"continue"}`) only when
there is a new item. It never blocks for checks still running (Claude Code and
Codex get a non-blocking notice), and it lets the agent stop:

- when a Stop hook already continued this turn (`stop_hook_active`,
  `continuation_active`) or Antigravity's `terminationReason` is not
  `NO_TOOL_CALL`;
- after three consecutive blocked turns in a session;
- when `PR_WATCH=0`, or `python3`, `git`, credentials or the network are
  missing, or GitHub's response cannot be read.

On SessionStart the same summary is added as context
(`additionalContext`, Antigravity `injectSteps`) and never blocks.

**Limits.** A hook only runs when the harness does something. An idle session
does not hear about CI that fails ten minutes after its last turn until it
next stops or resumes. Waking an idle session needs something outside the
harness (a scheduled `codex exec resume`, a GitHub Action), which this plugin
does not do. Claude Code cloud sessions that subscribe to pull request
activity get events pushed already; set `PR_WATCH=0` there to avoid hearing
about each one twice.

The Codex and Antigravity contracts used here are the ones the
`compose-preview` Stop gate already uses; a live block by this hook has not yet
been observed in either harness.
