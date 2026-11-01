---
name: harness-notes
description: Use whenever you change Compose UI code (composables, @Preview functions, themes) or render or review Compose previews, catalog components or UI Builder designs. Carries the mandatory cross-harness agent rules (R1–R4) and per-host notes for these tools.
---

# Harness notes

Workflows are in the `compose-preview` and `compose-ui-builder` skills; these are the shared rules
and per-host differences ([host setup](https://github.com/yschimke/compose-agent-plugins/blob/main/docs/host-setup.md)).

- **R1 — See what the user sees:** inspect the surface where the person will judge a visual change. After editing Compose UI source, call `render_preview` for an affected preview and look at the result before calling the change done; an edit you haven't rendered isn't done. If that surface is unavailable, say so and never claim to have seen the result from source or JSON alone. Never fake a render: no hand-built HTML, CSS or SVG mock of a preview; only real renders count, and a failed render is reported as failed.
- **R2 — Use typed tools with schemas:** prefer validated MCP or CLI operations; if raw JSON is unavoidable, validate it before saving and render it again afterwards.
- **R3 — Keep one canonical home:** read and preserve the design's recorded home, edit there in small batches, announce and reconcile temporary copies, and get approval before moving the home.
- **R4 — Keep discussion at the home:** use server comments for server-homed designs and the linked PR or issue for repo-homed designs, then report unacknowledged comments before finishing.

**Which server.** The person's own `@Preview`s come from the local `compose-preview-mcp` server;
library components and UI Builder designs from the hosted `compose-preview-catalog`. `ui.coo.ee/mcp`
is the same host as `preview.coo.ee/mcp`: use the installed entry, never add a second. R3 and R4
apply to UI Builder designs, not plain preview renders. A first local render may return `pending`
while the project starts: call again with the same arguments. Render options (`observe`, matrices,
recording) are in the `compose-preview` skill; whole-app runs are in its `references/simulator.md`.
Keep a simple render short: in Antigravity follow `antigravity-viewer-card`; elsewhere, one render
call and a short reply.

**Pickers.** `ui_builder_pick_branch` answers `ask-in-chat` where the host has no picker or form
(chat surfaces, Antigravity, CLI print modes): post its list and contact sheet and wait for a number.
`ui_builder_await_decision` with `waitSeconds: 0` is the poll for hosts that cannot hold a call open.

**Requested design review.** Load the `compose-preview` skill's
[catalog guidelines checklist](https://github.com/yschimke/skills/blob/main/skills/compose-preview/references/design-guidelines.md).
Claude Code, and OpenCode after `opencode-install.py`: use the packaged `design-reviewer` when it
is discoverable and delegation is allowed. Antigravity: `invoke_subagent(TypeName="self")` (it keeps
the plugin's MCP servers) with `Follow ~/.gemini/config/plugins/compose-preview/agents/design-reviewer.md: review only, no edits; local previews through compose-preview-mcp or the CLI, never the catalog server; return its compact verdict. Subject: <preview or design>.`;
with only `compose-catalogs` installed there is no such file, so hand it the checklist. Never
`define_subagent` (no plugin MCP servers). Codex, catalog-only installs and hosts without
delegation: run the checklist in the current context; never stop at a failed agent lookup. Use
the host's own tool names. Return the compact verdict, coverage and real evidence links on every
host; findings for a design with a home go there (R4). Partial evidence is partial coverage;
never invent an audit link.

**Connection recovery.** If a host shows an expired app connection, stop retrying and explain its
reconnect action; for an unknown `client_id`, follow host setup's recovery steps. Use
`request_access` only for a reachable server's `authorization_required`. Resolve a hosted catalog
from the hosted listing; don't clone it or start Gradle for it.

**Codex, checked-in designs.** `design_open` is a host file entrypoint (the host supplies
`file: {name, resourceUri}`); never invent `design_open(path=...)` or a hosted ID for a local file.
If the editor cannot open, keep working on the file with validation and real renders, and say so.

**Chat surfaces (Slack, Teams).** The person sees only text and attachments: attach or link each
render's signed `Image:` URL (valid 10 minutes), offer alternatives as a numbered
`catalog_render_matrix` contact sheet and take "2" as the choice. No server event wakes a chat
agent; poll `ui_builder_await_comments` / `ui_builder_await_decision` with `waitSeconds: 0`.

**Claude Code.** URL elicitation needs a 2026-07-28-protocol connection (≥2.1.281); otherwise use
the text fallback for the access grant. It does not load a plugin's `rules/AGENTS.md`.

Full contract: [`docs/agent-rules.md`](https://github.com/yschimke/compose-agent-plugins/blob/main/docs/agent-rules.md).
