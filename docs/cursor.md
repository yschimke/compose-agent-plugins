# Cursor

Cursor reads this repository's `.cursor-plugin/` manifests. The one install
command is in [host setup](host-setup.md#cursor); this page explains what it
does, the marketplace and team-marketplace options, MCP-only deeplinks, and the
check script.

## One-step install

`cursor-install.py` copies `plugins/compose-preview` (or `compose-catalogs` with
`--catalogs`) into `~/.cursor/plugins/local/<name>`:

| Piece | What Cursor gets |
| --- | --- |
| `.cursor-plugin/plugin.json` | Manifest with inline `mcpServers`, skills path, agents path, optional `variables`, and an empty inline `hooks` object |
| `skills/` | `compose-preview`, `compose-ui-builder`, `compose-preview-setup`, `harness-notes` (and the Antigravity card skill, unused here) |
| `agents/design-reviewer.md` | The read-only design reviewer |
| `mcpServers` in the manifest | Local `compose-preview mcp serve` and hosted `https://preview.coo.ee/mcp` |

It removes the other of `compose-preview` / `compose-catalogs` so they never
coexist, skips `.claude-plugin/` and `.codex-plugin/` trees, and refuses to leave
a broken copy. `--dry-run` prints the copies only. Run from a checkout to install
that checkout's generated plugins; otherwise it downloads the GitHub archive at
`--ref` (default `main`).

Then **Developer: Reload Window** (or restart Cursor). Open Customize and confirm
the plugin, its skills and both MCP servers. Ask: **"render the
`ListScreenPreview`"** (one of your own preview names).

Local renders still need the `compose-preview` CLI on `PATH`. When it is missing,
the plugin's `compose-preview-setup` skill installs it, or run the
[skills installer](https://github.com/yschimke/skills/blob/main/scripts/install.sh).
Do not also run `compose-preview mcp install` for Cursor host registration: the
plugin already declares the servers, and the CLI does not write
`~/.cursor/mcp.json` today.

Verify from a checkout:

```sh
python3 scripts/cursor-check.py
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
manifests that pass Cursor's published schemas in CI. Public listing still needs
a smoke test and a submission at
[cursor.com/marketplace/publish](https://cursor.com/marketplace/publish)
([#59](https://github.com/yschimke/compose-agent-plugins/issues/59),
[#81](https://github.com/yschimke/compose-agent-plugins/issues/81)).

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

## MCP-only deeplinks (not the default)

Prefer the plugin. If you only need one server and no skills, Cursor's
[MCP install links](https://cursor.com/docs/mcp/install-links) add a single entry
to `mcp.json` after a prompt:

- Hosted catalog:
  `cursor://anysphere.cursor-deeplink/mcp/install?name=compose-preview-catalog&config=eyJ1cmwiOiJodHRwczovL3ByZXZpZXcuY29vLmVlL21jcCJ9`
- Local daemon (needs the CLI on `PATH`):
  `cursor://anysphere.cursor-deeplink/mcp/install?name=compose-preview-mcp&config=eyJjb21tYW5kIjoiY29tcG9zZS1wcmV2aWV3IiwiYXJncyI6WyJtY3AiLCJzZXJ2ZSJdfQ==`

Do not add both deeplinks **and** the plugin: every tool would appear twice.

## VS Code extension

The [Compose Preview](https://marketplace.visualstudio.com/items?itemName=yuri-schimke.compose-preview)
VS Code extension also runs in Cursor and renders `@Preview`s inline in the
editor. It is a separate product surface from the agent plugin: use it when you
want the preview pane yourself; use the plugin when the agent should call
`render_preview`.
