# Troubleshooting

Each entry is a problem we have hit, what causes it, and the fix. In
Antigravity, run `python3 scripts/antigravity-check.py` first: it checks most of
these. In OpenCode, run `python3 scripts/opencode-check.py`.

## `compose-preview: command not found`

- **New install:** the installer adds `~/.local/bin` to your bash, zsh and fish
  startup files. Open a new terminal, or restart the harness so it inherits the
  new `PATH`. With fish, check that `~/.local/bin` is in `fish_user_paths`.
- **Worked before, then stopped:** `~/.local/bin/compose-preview` may be a
  broken link. An older `npx skills add`/`update` wiped the CLI it pointed at
  (fixed in yschimke/skills#101). Reinstall the CLI only, as in the skills'
  [setup guide](https://github.com/yschimke/skills/blob/main/skills/compose-preview/references/setup.md).

## `render_preview: project not prepared`

The project's Gradle build hasn't been set up for rendering yet. The full
message ends with "the build does not apply the Compose Preview plugin and no
compose-preview init script was found; run `compose-preview mcp install` once".
From the project's root folder:

```sh
compose-preview mcp install
```

If that fails with "SDK location not found", set `ANDROID_HOME`, or put
`sdk.dir=/path/to/android-sdk` in the project's `local.properties`, and run it
again.

## Two `compose-preview` servers in Claude Code

`compose-preview mcp install` can also register a global `compose-preview-mcp`
server beside the plugin's own. CLI 2.28.4 did this when `CLAUDE_CONFIG_DIR` was
set, and it suggested installing the plugin although it was installed (#87). If
`claude mcp list` shows both `compose-preview-mcp` and
`plugin:compose-preview:compose-preview-mcp`, remove the global one:

```sh
claude mcp remove compose-preview-mcp --scope user
```

## Two `compose-preview` servers in Antigravity

Older versions of `compose-preview mcp install` also wrote a global
`compose-preview-mcp` entry to `~/.gemini/antigravity/mcp_config.json` (or
`~/.gemini/config/mcp_config.json`) that duplicates the plugin's server. This
was fixed in yschimke/compose-ai-tools#5641, so run `compose-preview update`
first. An entry that an older CLI already wrote stays: delete any
`compose-preview*` entry from `mcpServers` in that file and restart
Antigravity.

## Every catalog tool appears twice

The hosted server is configured twice, usually once as `https://preview.coo.ee/mcp`
and once as `https://ui.coo.ee/mcp`. They are the same server, so remove the
`ui.coo.ee/mcp` entry and keep `preview.coo.ee/mcp`; see
[local and hosted MCP servers](host-setup.md#local-and-hosted-mcp-servers).

## Stale `mcp serve` processes

After a CLI update, servers from the old version can keep running and answer
instead of the new one. List them and kill the old ones, then restart the
harness:

```sh
ps -axo pid=,command= | grep 'compose-preview.*mcp serve'
```

## Antigravity card says "bridge unavailable"

The card came from an old plugin that expected an MCP Apps bridge, which
Antigravity does not have. Antigravity copies plugins at install time, so
uninstall and reinstall to pick up `main`: rerun the
[install script](host-setup.md#antigravity), which does both.

## Antigravity `compose-preview` has no skills or hooks

`agy plugin install https://github.com/yschimke/compose-agent-plugins` (the bare
repository URL) reads the root `gemini-extension.json` and installs only its two
MCP servers, listed in `agy plugin list` with `"source": "gemini-cli"`. Uninstall
it, then install the plugin folder with the `/tree/main/plugins/compose-preview`
URL ([host setup](host-setup.md#antigravity)); `scripts/antigravity-install.py`
does both.

## The render does not show my edit

Needs the next compose-preview-server release after 3.78.0, which re-renders
after the edit notification without a Gradle build (plugin side: #49). Update with
`compose-preview update`. Don't run Gradle yourself, and don't ask the agent to;
that only slows the loop. If renders still look out of date, clear the server
cache and restart the harness:

```sh
rm -rf ~/.cache/composeai/preview-mcp
```

This step is needed until yschimke/compose-ai-tools#5602 ships.

## The agent greps and reads docs before rendering

A routine "render the `<PreviewName>`" should be one `render_preview` call and
a short reply. If the agent registers projects, greps for the preview or reads
skills first, the plugin or server is old. Run `compose-preview update`, update
the plugin (reinstall in Antigravity), and start a new session.

## OpenCode config was not updated

`compose-preview mcp install --opencode` never rewrites a `.jsonc` file or a
file with comments. It prints the snippet and the file it belongs in instead;
paste it in by hand. See [OpenCode](opencode.md#let-the-cli-write-the-local-server).
`python3 scripts/opencode-check.py` prints the same snippet when it finds a
JSONC config without `compose-preview-mcp`. Re-running `mcp install` does not
help.

## `compose-preview: command not found` after reinstalling the skills

Older CLI installs lived inside the `compose-preview` skill folder, so
`npx skills add … compose-preview` removes them along with the old skill. Run
the installed skill's bootstrap once to put the CLI back on `PATH`:

```sh
bash ~/.agents/skills/compose-preview/scripts/compose-preview --version
```

It installs into `~/.local/share/compose-preview`, which skill reinstalls leave
alone.

## `mcp install` times out

The first `compose-preview mcp install` bootstraps the descriptor and resolves
the project through Gradle, which can take several minutes on a cold machine.
An agent shell with a 120 s limit cancels it (`Interrupted — cancelling Gradle
build...`). Run it in a terminal, or give the command a 10-minute timeout.

## OpenCode rejects reading the rendered PNG

`render_preview` succeeds, but reading its `pngPath` fails with `The user
rejected permission to use this specific tool call.` in `opencode run`, or
asks for `external_directory` access in the TUI. The PNG is in the server's
temporary directory, outside the project. Allow those directories in your
OpenCode config, as in [OpenCode → Let OpenCode read rendered
PNGs](opencode.md#let-opencode-read-rendered-pngs); `scripts/opencode-check.py`
prints the snippet when it is missing.

## Codex hooks are marked untrusted

Codex registers the plugin's SessionStart, PostToolUse and Stop hooks as
`untrusted` until you approve them. Approve them when Codex asks, or from
`/plugins`. The Stop gate stays off unless `COMPOSE_PREVIEW_GATE=1` is set.

## Codex lists no `compose-preview-catalog`

`codex mcp list` shows `compose-preview-mcp` but not `compose-preview-catalog`
when only the `compose-preview` plugin is enabled, or when the
`compose-preview-mcp` entry is one you registered by hand rather than the
plugin's. Run `codex plugin list` and check that
`compose-catalogs@compose-agent-plugins` is `installed, enabled`; if not, enable it
from `/plugins` and start a new session. Seen in the
[2026-10-02 Codex smoke run](https://github.com/yschimke/compose-agent-plugins/issues/76#issuecomment-5950380878).

## "no project registered" in Codex Desktop

Codex Desktop starts each chat in its own worktree of whichever repository you
opened, so the server's working directory is often not the Gradle build. The
error lists what it tried and ends with `Candidate builds: <path>`. Pass that
path as `project` on the first `render_preview`; later calls in the session
reuse it. Opening the Gradle build's folder in Codex avoids the extra call.

## "Semantics unavailable" or pixel-only checks

The agent reports that `compose/semantics` is not available on the local
daemon and checks layout from the bitmap instead. This costs more tokens, and
`crop` by `testTag` and `diff_semantics` stop working. Tracked in
yschimke/compose-preview-server#1166; no workaround yet.
