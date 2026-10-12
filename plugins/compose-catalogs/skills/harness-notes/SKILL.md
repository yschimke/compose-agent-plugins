---
name: harness-notes
description: Use whenever you change Compose UI code (composables, @Preview functions, themes) or render or review Compose previews, catalog components or UI Builder designs. Carries the mandatory cross-harness agent rules for compose-agent-plugins's tools, alongside the canonical yschimke/skills workflows.
---

# Harness notes

Use the canonical `compose-preview` and `compose-ui-builder` skills from
[`yschimke/skills`](https://github.com/yschimke/skills) for workflows. These notes only carry the
rules that must remain consistent across Antigravity, Claude Code, Codex and OpenCode. Per-host install, MCP registration, cloud sandbox and CI session details are in
[`docs/host-setup.md`](https://github.com/yschimke/compose-agent-plugins/blob/main/docs/host-setup.md).

- **R1 — See what the user sees:** inspect the surface where the person will judge a visual change. After editing Compose UI source, call `render_preview` for an affected preview and look at the result before calling the change done; an edit you haven't rendered isn't done. If that surface is unavailable, say so and never claim to have seen the result from source or JSON alone. Never fake a render: no hand-built HTML, CSS or SVG mock of a preview; only real renders count, and a failed render is reported as failed.
- **R2 — Use typed tools with schemas:** prefer validated MCP or CLI operations; if raw JSON is unavoidable, validate it before saving and render it again afterwards.
- **R3 — Keep one canonical home:** read and preserve the design's recorded home, edit there in small batches, announce and reconcile temporary copies, and get approval before moving the home.
- **R4 — Keep discussion at the home:** use server comments for server-homed designs and the linked PR or issue for repo-homed designs, then report unacknowledged comments before finishing.

UI Builder workflows (check before showing, device grid, branches, approval and handoff to code) are in
the canonical `compose-ui-builder` skill. Host notes only: `ui_builder_pick_branch` answers `ask-in-chat`
where the host has no picker or form (chat surfaces, Antigravity, CLI print modes); post its list and
contact sheet and wait for the person's number. `ui_builder_await_decision` with `waitSeconds: 0` is the
poll for hosts that cannot hold a long call open.

Pick the server by what is being rendered: the person's own `@Preview`s come from the local
`compose-preview-mcp` server; library components come from `compose-preview-catalog`. R3 and R4
apply to UI Builder designs, not to plain preview renders. Keep a simple render short: in Antigravity,
follow `antigravity-viewer-card` (`render_preview preview=<Name>`, look at the PNG, a few bullets); elsewhere, one
render call and a short reply.

**Requested design review.** Load the canonical `compose-preview` skill's
[catalog guidelines checklist](https://github.com/yschimke/skills/blob/main/skills/compose-preview/references/design-guidelines.md).
In Claude Code, or OpenCode with `opencode-install.py` run, use the packaged
`design-reviewer` when it is discoverable and the task allows delegation. In
Antigravity, delegate with `invoke_subagent(TypeName="self")`, which keeps the
plugin's `compose-preview_compose-preview-mcp` server, and hand it the
reviewer's instructions, since `self` does not carry them or its review-only
boundary: "Follow ~/.gemini/config/plugins/compose-preview/agents/design-reviewer.md: review only, no edits; local previews through compose-preview-mcp or the CLI, never the catalog server; return its compact verdict. Subject: <preview or design>." With only `compose-catalogs` installed there is no such file; hand it the
canonical checklist instead. Never use `define_subagent` for it: such a subagent is not
granted plugin-scoped MCP servers. In Codex, a catalog-only install or any host
without delegation, run the same checklist in the current context; never stop
at a failed agent lookup. Use this host's advertised tool
names and schemas rather than copying Claude's namespace. Review records are
metadata at the design's home, not node edits or human approval. Missing frames,
stale results and skipped rules produce partial coverage, not a clean pass.

**Show audit results.** Return the compact verdict, subject/revision, freshness,
answered/unchecked coverage and evidence links in chat on every host. In
Codex Desktop or another MCP Apps host, request advertised render `details`
for a requested accessibility/layout audit so the person can inspect findings
and overlays in the viewer; fetch full data separately if the tool only returns
a summary. Guideline verdicts are separate from those measured checks. For a
UI Builder review saved with `ui_builder_record_guidelines`, return the real
editor URL and point to its Issues panel. Say when a review could not be saved.
The server viewer may offer **Review design guidelines**, sending the current
subject to chat, or a copyable prompt when messages are unavailable. For UI
Builder subjects, **Show saved review** can display the recorded model,
revision, coverage and findings when the tool is advertised. Follow the
canonical checklist for that request; no paid provider run is implied. In CLI,
OpenCode, static cards and chat surfaces, return the same compact verdict and
coverage with real artifact links/paths and a follow-up prompt when useful.
Include detailed findings directly only for subjects without a recorded home.
For server-homed designs, keep findings and discussion in server comments when
authorized; for repo-homed designs, use the linked PR or issue. Chat returns
home/thread links instead of duplicating that discussion. If posting is
unavailable, report the limitation and intended destination. Never invent
an audit-launch link or claim a request is a finished review.

**Hosted reviews and connection recovery.** For a published catalog or a
server-homed design, start with advertised catalog/design tools. Resolve a named
catalog from the hosted listing; do not clone it, register a local project,
start Gradle or provision a cloud environment just because its checkout is
absent. Request source only when the review needs unavailable source evidence
or the task explicitly includes code changes. If Codex/ChatGPT or another host
shows an expired app connection, stop retrying that connection and explain the
reconnect action. If the person declines it, continue independent local/source
work without invoking tools that repeat the authorization prompt. If the
browser reports an unknown `client_id`, stop retries: reinstalling a marketplace
plugin may retain the same app and rejected OAuth client ID. The operator must
restore its trusted registration, or the host must create a fresh app/registration.
If the app ID changes, update the plugin's app reference and regenerate its
manifests. Follow the marketplace recovery steps in the host setup notes;
retrying the old link cannot work.
Use `request_access` only for a reachable server's `authorization_required`
response, not to repair host OAuth. Network/proxy failures do not prove a grant
expired. Report blocked evidence and resume after reconnection.

**Local startup.** The first local render in a session prepares the project: a Gradle bootstrap the first
time a build is seen (minutes when cold), then the render daemon (about 15–20 s), so a first
`render_preview` can come back `pending` or take far longer than the next one. When the result is
`pending`, call `render_preview` again with the same arguments; don't treat it as a failure or switch
to Gradle. Say once that the first render is slow because the project is starting. When a task will
need a render later but doesn't start with one (you are reading or editing Compose UI first), call
`register_project` with the workspace path as soon as you know: it returns at once and prepares the
project in the background while you work. Skip it when the first request is itself a render, because
`render_preview` does the same preparation and the extra call only adds a turn.

**Checked-in designs in Codex.** Use the canonical UI Builder skill's
[local design-to-code workflow](https://github.com/yschimke/skills/blob/main/skills/compose-ui-builder/references/local-design-to-code.md).
`design_open` is a host file entrypoint: the host supplies
`file: {name, resourceUri}` and the `openai/resource` capability. Do not invent
`design_open(path=...)`, a resource URI, or a hosted design ID for a local file.
If this Codex surface cannot open the editor, keep working on the canonical
file with validation and real renders, and report that editor collaboration
was unavailable. Opening a local file does not require hosted OAuth.

In an available editor panel, use stable selected node IDs and comment context;
the panel is for selection, comments and quick property edits. Present actual
device renders and reference comparisons in chat. Preserve concurrent user
edits; reconcile a file revision/ETag conflict before saving. Continue through
requested design edits, code adaptation and application preview verification;
a model review record is not a person's approval. Never claim real Codex
acceptance from a simulated MCP host test.

In a chat surface (Claude in Slack, Teams), the person sees only text and attachments. Each render from
the hosted catalog carries a signed https PNG (an `Image: <url>` line, `imageUrl`, `contactSheet.url`)
that is valid for 10 minutes: attach or link that, and never describe an image from memory. To offer
alternatives, call `catalog_render_matrix` with `observe=png`, post its numbered contact sheet with the
options, and take the person's reply ("2") as the choice. Reactions and buttons are not input there. For
R4, post the design link and a summary of unacknowledged comments rather than treating thread replies as
design comments. No server event wakes a chat agent, so follow up through a PR subscription or by polling
`ui_builder_await_comments` / `ui_builder_await_decision` with `waitSeconds: 0`.

Claude Code ≥2.1.281 supports URL elicitation only on 2026-07-28-protocol connections; otherwise use the text fallback for the access grant.
Claude Code does not load a plugin's `rules/AGENTS.md`; guidance it must always see belongs in a skill or the SessionStart message.

The full, authoritative contract and current tooling gaps are in
[`docs/agent-rules.md`](https://github.com/yschimke/compose-agent-plugins/blob/main/docs/agent-rules.md).
