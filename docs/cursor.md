# Cursor

Cursor reads this repository's `.cursor-plugin/` manifests. The one install
command is in [host setup](host-setup.md#cursor); this page explains what it
does, the marketplace and team-marketplace options, MCP-only deeplinks, the
check/smoke scripts, and how preview + audit fit next to the VS Code extension.

## One-step install

`cursor-install.py` copies `plugins/compose-preview` (or `compose-catalogs` with
`--catalogs`) into `~/.cursor/plugins/local/<name>`:

| Piece | What Cursor gets |
| --- | --- |
| `.cursor-plugin/plugin.json` | Manifest with inline `mcpServers`, skills path, agents path, optional `variables`, marketplace `logo`, and an empty inline `hooks` object |
| `skills/` | `compose-preview`, `compose-ui-builder`, `compose-preview-setup`, `harness-notes` (and the Antigravity card skill, unused here) |
| `agents/design-reviewer.md` | The read-only design reviewer (preview + catalog guidelines audit) |
| `mcpServers` in the manifest | Local `compose-preview mcp serve` and hosted `https://preview.coo.ee/mcp` |
| `assets/compose-preview-logo.png` | Marketplace logo (same mark as the VS Code extension) |

It removes the other of `compose-preview` / `compose-catalogs` so they never
coexist, skips `.claude-plugin/` and `.codex-plugin/` trees, and refuses to leave
a broken copy. `--dry-run` prints the copies only. `--review` also installs the
optional `compose-review` plugin (PR review and preview-CI skills) alongside the
primary one. Run from a checkout to install that checkout's generated plugins;
otherwise it downloads the GitHub archive at `--ref` (default `main`).

Then **Developer: Reload Window** (or restart Cursor). Open Customize and confirm
the plugin, its skills, `design-reviewer`, and both MCP servers. Start with
preview and audit:

1. **"render the `ListScreenPreview`"** (one of your own `@Preview` names), or a
   hosted catalog component if you have no local Java.
2. **"review that preview against its catalog design guidelines"** (or invoke
   `design-reviewer`). Ask for accessibility / layout details on the same render.

Leave UI Builder for a later pass; the smoke below does the same.

Local renders still need the `compose-preview` CLI on `PATH`. When it is missing,
the plugin's `compose-preview-setup` skill installs it, or run the
[skills installer](https://github.com/yschimke/skills/blob/main/scripts/install.sh).
Do not also run `compose-preview mcp install` for Cursor host registration: the
plugin already declares the servers, and the CLI does not write
`~/.cursor/mcp.json` today.

Verify from a checkout:

```sh
python3 scripts/cursor-check.py
python3 scripts/cursor-smoke.py --check-only   # packaging + logo + reviewer
```

## Why not the skills installer alone?

The generic
[`install.sh`](https://github.com/yschimke/skills/blob/main/scripts/install.sh)
path still works, but it only drops the CLI and skills. You then have to add both
MCP servers by hand (or via deeplinks below). The Cursor plugin is the Level 1
install because it is one step and matches Claude Code / Codex / Antigravity:
skills, agents and both servers together.

## Marketplace and team marketplaces

This repository already ships `.cursor-plugin/marketplace.json` and per-plugin
manifests that pass Cursor's published schemas in CI. `compose-preview` and
`compose-catalogs` set `logo` to `./assets/compose-preview-logo.png` (copied from
the VS Code extension icon, Apache-2.0, same author).

### Submission checklist (#81)

Do this only after the [live smoke](#smoke-test-preview--audit) passes:

1. Confirm CI's Cursor schema job is green on `main`.
2. Confirm each submitted plugin's `.cursor-plugin/plugin.json` has `name`,
   `displayName`, `description`, `logo` (preview/catalogs), and working
   `mcpServers` / `skills` / `agents` as generated.
3. Submit `https://github.com/yschimke/compose-agent-plugins` at
   [cursor.com/marketplace/publish](https://cursor.com/marketplace/publish).
   Cursor reads the root `.cursor-plugin/marketplace.json` (multi-plugin repo).
4. Record the review outcome and how updates are picked up under
   [#59](https://github.com/yschimke/compose-agent-plugins/issues/59).

On Teams or Enterprise, an admin can import
`https://github.com/yschimke/compose-agent-plugins` as a team marketplace under
Dashboard → Plugins & MCPs. Cursor parses `.cursor-plugin/marketplace.json` and
teammates install `compose-preview` from Customize. Prefer that over
`~/.cursor/plugins/local` when the team already uses marketplaces; keep one
install path per machine (local **or** marketplace, not both for the same name).

## Hooks and the token

`compose-preview` sets `"hooks": {"version": 1, "hooks": {}}` in the Cursor
manifest so Cursor does not load the Claude Code `hooks/hooks.json` next to it.
Whether that empty inline config fully suppresses discovery is part of the
[#79](https://github.com/yschimke/compose-agent-plugins/issues/79) smoke test.

The optional `COMPOSE_PREVIEW_TOKEN` is declared under `variables` and referenced
as `${COMPOSE_PREVIEW_TOKEN}` in the hosted server's headers. Leave it blank to
use the interactive access grant. Expansion through plugin variables is
unverified until that smoke test.

## Smoke test (preview + audit)

```sh
python3 scripts/cursor-smoke.py
```

`--check-only` stops after packaging checks (logo, empty hooks, token variable,
`design-reviewer`, optional schema validate). Without it, the script starts a
local header-echo MCP, prints the live steps, and waits for Enter.

Live half (record under `docs/evidence/` and update
[harness-matrix](harness-matrix.md)):

| Step | Expect |
| --- | --- |
| Install + Reload | Customize lists plugin, both MCP servers, `compose-preview` skill, `design-reviewer` |
| Catalog or local render | Tool result shows PNG + text; ask for a11y/layout details |
| Guidelines audit | Compact verdict via `preview_guidelines_prompt` / `design-reviewer` on that preview |
| Hooks | No compose-preview hooks listed |
| Token (optional echo) | Unset → empty header; set `smoke-cursor-token` → header matches; then `cursor-install.py` + Reload to drop the echo `compose-catalogs` |
| MCP App | Iframe may stay on "Waiting…"; chat image/text still counts (R1) |

UI Builder designs are intentionally out of this smoke; use
[design-guidelines-review](design-guidelines-review.md) once preview audit is green.

## MCP-only deeplinks (not the default)

Prefer the plugin. If you only need one server and no skills, Cursor's
[MCP install links](https://cursor.com/docs/mcp/install-links) add a single entry
to `mcp.json` after a prompt:

- Hosted catalog:
  `cursor://anysphere.cursor-deeplink/mcp/install?name=compose-preview-catalog&config=eyJ1cmwiOiJodHRwczovL3ByZXZpZXcuY29vLmVlL21jcCJ9`
- Local daemon (needs the CLI on `PATH`):
  `cursor://anysphere.cursor-deeplink/mcp/install?name=compose-preview-mcp&config=eyJjb21tYW5kIjoiY29tcG9zZS1wcmV2aWV3IiwiYXJncyI6WyJtY3AiLCJzZXJ2ZSJdfQ==`

Do not add both deeplinks **and** the plugin: every tool would appear twice.

## Three surfaces (do not confuse them)

| Surface | Install | What you see |
| --- | --- | --- |
| Cursor plugin (`cursor-install.py`) | Local plugin or marketplace | Skills, `design-reviewer`, MCP tools in chat |
| MCP App viewer | Comes with the MCP servers above | Interactive card **inline in chat** after a render tool |
| [VS Code extension](https://marketplace.visualstudio.com/items?itemName=yuri-schimke.compose-preview) | Extensions view | Human preview **panel** in the editor |

The plugin does not open a right-hand IDE pane. Plugin canvases (Hex / Atlassian
style templates in Customize) are a different Cursor feature and are not this
viewer.

## MCP Apps in Cursor

Cursor supports MCP Apps and will open `ui://compose-preview/viewer` when a
catalog or local render tool advertises it. Live check (2026-11-02): the iframe
mounts, but Cursor does not always push `ui/notifications/tool-result` into it,
so the card can sit on **Waiting for a preview result…** while the real PNG and
text still appear in the normal tool result below. Until that host gap closes:

- Treat the tool result's image and text as the source of truth (R1).
- Do not wait on the empty viewer shell, and do not claim the render failed only
  because the iframe is empty.
- Re-check after Cursor updates; record the outcome against
  [#79](https://github.com/yschimke/compose-agent-plugins/issues/79).

## Cloud Agents

Cloud Agents do **not** load `~/.cursor/plugins/local` or a project
`.cursor/mcp.json` from the IDE install. Attach MCP for them separately:

1. Personal: [cursor.com/agents](https://cursor.com/agents) → MCP dropdown → add
   HTTP server `compose-preview-catalog` at `https://preview.coo.ee/mcp`, enable
   it, then start a **new** agent.
2. Team: Dashboard → Plugins & MCPs → Team MCP servers (same URL). Optional:
   Add to Team Marketplace so the IDE gets the same server.

Prefer HTTP for Cloud Agents. That path is enough for hosted catalog renders and
catalog guidelines audit. Local `compose-preview mcp serve` (stdio) needs the
CLI and Java in the cloud environment image and is a separate setup.

## VS Code extension (human preview pane)

The [Compose Preview](https://marketplace.visualstudio.com/items?itemName=yuri-schimke.compose-preview)
VS Code extension also runs in Cursor (`engines.vscode` ^1.115) and is the
right-hand / activity-bar preview surface for a person. It is separate from the
agent plugin.

- Open the **Compose Preview** view; it scopes to the active Kotlin preview
  source (`EditorScope`) and refreshes when that file changes or is saved.
- Focus on the webview does not blank the panel: sticky scope keeps the last
  preview file until you switch to another preview source or close its tab.
- Use **Compose Preview: Refresh Previews** / **Render All Previews** from the
  command palette; CodeLens on `@Preview` functions jumps focus into the panel.
- Same Gradle daemon / `build/compose-previews/` tree the CLI and local MCP use
  when the project is prepared.

Practical combo: Cursor plugin for the agent (render + audit in chat) + this
extension for the human pane. Install the extension from the Extensions view
when you want that pane; do not expect the agent plugin to dock one.
