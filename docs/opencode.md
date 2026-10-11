# OpenCode

OpenCode does not use this repository's plugin manifests or marketplace.
Configure its MCP servers directly and install the canonical skills from
`yschimke/skills`.

This guide uses the current OpenCode v2 configuration shape: server definitions live under `mcp.servers`, and `disabled` (rather than `enabled`) controls whether a configured server connects. OpenCode 1.18 (the npm `latest`) also reads this shape, so `scripts/opencode-check.py` accepts 1.18 and later. See the [OpenCode MCP documentation](https://opencode.ai/v2/docs/mcp-servers) for the current contract.

## One-step install

```sh
npx skills add yschimke/skills --global --yes --skill compose-preview --skill compose-ui-builder
curl -fsSL https://raw.githubusercontent.com/yschimke/compose-agent-plugins/main/scripts/opencode-install.py | python3 -
compose-preview mcp install --opencode   # from the Compose project root; prepares it and pins --project
```

`opencode-install.py` copies the generated [`opencode/`](../opencode) bundle into
`$XDG_CONFIG_HOME/opencode` (default `~/.config/opencode`):

| File | What it gives OpenCode |
| --- | --- |
| `agents/design-reviewer.md` | The read-only review subagent that Claude Code and Antigravity get from the plugin. It is generated from the same source with the same boundary: no edits, `bash` limited to the `compose-preview` and `gh` commands the Claude agent allows, and only the review tools of both MCP servers. |
| `skills/harness-notes/SKILL.md` | The cross-harness agent rules (R1–R4) that the wiring plugins carry elsewhere. |
| `plugins/compose-preview.js` | The post-edit render reminder: after `edit`, `write` or `apply_patch` touches a `*.kt` file with a `@Composable` or `@Preview`, it appends one line to that tool's result asking for a render before the change is called done. Once per file per session; it never blocks. |

It then adds `compose-preview-mcp`, `compose-preview-catalog` and the
[rendered-PNG read rule](#let-opencode-read-rendered-pngs) to `opencode.json`,
keeping every existing key and any server entry already there (such as the one
`mcp install --opencode` writes with `--project`). A config already in the v1
`mcp.<name>` shape gets v1 entries. It never rewrites `opencode.jsonc` or a file
with comments; it prints the snippet to merge instead. `--dry-run` prints what
would change, and rerunning it updates the bundle. The sections below describe
the same configuration by hand.

## MCP servers

Create `opencode.jsonc` in the Compose project (or `.opencode/opencode.jsonc`), or add the same object to `~/.config/opencode/opencode.jsonc` for every project. The local `compose-preview-mcp` server requires Java 17, Gradle, and the `compose-preview` CLI on `PATH`.

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "compose-preview-mcp": {
        "type": "local",
        "command": ["compose-preview", "mcp", "serve"],
        "codemode": false
      },
      "compose-preview-catalog": {
        "type": "remote",
        "url": "https://preview.coo.ee/mcp",
        "headers": {
          "X-Compose-Preview-Token": "{env:COMPOSE_PREVIEW_TOKEN}"
        },
        "codemode": false
      }
    }
  }
}
```

`codemode: false` exposes the individual tools directly. OpenCode prefixes them with the server name, so the two `render_preview` tools are distinct: `compose-preview-mcp_render_preview` and `compose-preview-catalog_render_preview`. Omit `codemode: false` if you prefer OpenCode's default Code Mode grouping.

### Let the CLI write the local server

`compose-preview` 2.28.0 and later can register the local server for you. Run it from the Compose project root:

```sh
compose-preview mcp install --opencode                  # user scope: ~/.config/opencode/opencode.json
compose-preview mcp install --opencode --scope project  # project scope: ./opencode.json
```

It upserts `mcp.servers.compose-preview-mcp` with `--project=<absolute project path>` and keeps every other key. It never rewrites a `.jsonc` file or a file with comments. For those it prints the snippet and the file to merge it into by hand; `scripts/opencode-check.py` prints the same snippet. The first run resolves the project through Gradle and can take several minutes, so give an agent shell a 10-minute timeout. Plain `compose-preview mcp install` also selects OpenCode automatically when `opencode` is on `PATH`, `~/.config/opencode/` exists, or `OPENCODE=1` is set. It does not add the remote catalog server; add that entry from the block above.

Check the connections after restarting OpenCode:

```sh
opencode mcp list
```

### Let OpenCode read rendered PNGs

`render_preview` writes each PNG to its own temporary directory, such as
`/private/var/folders/…/T/compose-preview-mcp-943320557216657247/<sha>.png`.
That is outside the project, so OpenCode's `external_directory` permission
asks before the agent can read it, and a non-interactive `opencode run`
rejects the ask (`The user rejected permission to use this specific tool
call.`). Allow just those directories:

```jsonc
{
  "permission": {
    "external_directory": {
      "*/compose-preview-mcp-*": "allow"
    }
  }
}
```

OpenCode's `*` matches any characters, including `/`, so the rule covers the
server's temporary directories wherever the platform puts them, and nothing
else outside the project. Reads there are then allowed by the default `read`
rule. Without it an interactive session can still answer the prompt; an eval
or scripted run cannot ([#105](https://github.com/yschimke/compose-agent-plugins/issues/105)).

## Skills

Install the canonical Compose skills through the Skills CLI:

```sh
npx skills add yschimke/skills --global --yes --skill compose-preview --skill compose-ui-builder
```

This installs the skills into `~/.agents/skills`, which OpenCode reads, and also sets them up for any other agents the Skills CLI detects. Add `--agent opencode` to set up OpenCode only. The files land in the same `~/.agents/skills` directory.

This repository deliberately carries no copies of `compose-preview` or
`compose-ui-builder`. Their detailed workflows, including catalog access, live
preview rendering, and UI Builder operations, remain in `yschimke/skills` so
all harnesses use one source of truth. Do not install a same-named local copy on
top of them.

For a design review, the default skills include the
[catalog guidelines checklist](https://github.com/yschimke/skills/blob/main/skills/compose-preview/references/design-guidelines.md).
With the bundle installed, delegate it to the `design-reviewer` subagent
(`@design-reviewer`); otherwise run it in the current context. Discover the tools on the configured server; direct
tool names use its prefix (for example
`compose-preview-mcp_preview_guidelines_prompt`), or use the advertised Code
Mode interface when enabled. The checklist needs neither MCP Apps nor
elicitation nor a provider key for agent judgment. See
[review setup and fallbacks](design-guidelines-review.md).

Alternatively, from a checkout of `yschimke/skills`, symlink the two skill
directories into OpenCode's global skill directory:

```sh
mkdir -p ~/.config/opencode/skills
ln -s "$(pwd)/skills/compose-preview" ~/.config/opencode/skills/compose-preview
ln -s "$(pwd)/skills/compose-ui-builder" ~/.config/opencode/skills/compose-ui-builder
```

Run those commands from the `yschimke/skills` repository root. OpenCode also
discovers compatible skills at `.claude/skills`, `.agents/skills`,
`~/.claude/skills`, and `~/.agents/skills`; avoid installing another skill with
the same ID unless you mean to override it. See the
[OpenCode skills documentation](https://opencode.ai/v2/docs/skills) for
discovery order and precedence.

## Authentication

The hosted catalog supports either an interactive OAuth grant or a preview-service token.

For OAuth, leave `oauth` unset (it is enabled for remote servers by default), then start the browser flow:

```sh
opencode mcp auth compose-preview-catalog
```

You can also use OpenCode's `/mcps` command and select the catalog server. OpenCode discovers the authorization server, uses PKCE, and stores the resulting credentials outside `opencode.jsonc`.

For token authentication, set the token in the environment before starting OpenCode:

```sh
export COMPOSE_PREVIEW_TOKEN='…'
opencode
```

The config passes it through the `X-Compose-Preview-Token` header. Do not put the token directly in `opencode.jsonc` or commit it. If a token-only deployment must never attempt OAuth, add `"oauth": false` to the `compose-preview-catalog` server entry.

## Check the setup

From a clone of this repository:

```sh
python3 scripts/opencode-check.py                                   # read-only, no model
python3 scripts/opencode-check.py --run --project ~/path/to/app     # plus a cold and a warm render turn
```

It prints one line per check (`ok`, `FIX` or `info`). Each plain `opencode run` starts its own
`compose-preview mcp serve`, so every such turn renders cold. `--run` therefore starts one
`opencode serve` in the project and attaches both turns to it: turn 1 is the cold render (T1 in
[`evals/token-budget.md`](../evals/token-budget.md), time recorded only) and turn 2, in a new session
against the same warm server, is held to the 30 s T2 budget. Each turn splits its time between the
render and OpenCode's own startup and model calls. For fixes, see
[Troubleshooting](troubleshooting.md).

## Verification record

Checked on 2026-10-10 with `opencode-ai@1.18.35` (the npm `latest`), each run in an empty `HOME`
and `XDG_CONFIG_HOME`. No real model; the plugin turn used a scripted OpenAI-compatible endpoint.

| Check | Command | Result |
| --- | --- | --- |
| Bundle discovery | `opencode-install.py`, then `opencode agent list` and `opencode debug skill` | `design-reviewer (subagent)` listed; `harness-notes` listed from `skills/`. OpenCode 1.18.35 reads both `agent/` and `agents/`, `plugin/` and `plugins/`. |
| Reviewer boundary | `opencode debug agent design-reviewer` | `edit` denied; `bash` denied except the nine allowed prefixes; each server's `*` tools denied, then the 42 review tools allowed after them (last match wins). |
| Edit reminder | `opencode run` against a scripted model that calls `write` on `Screen.kt` (`@Composable`) | The tool result sent back to the model was `Wrote file successfully.` followed by the reminder line. |
| Config merge | `opencode-install.py` on an empty config, a v1 `mcp.<name>` config, a v2 `mcp.servers` config and an `opencode.jsonc`; then `opencode mcp list` | Existing `compose-preview-mcp` entries and other keys kept. `compose-preview-catalog` connected in all three JSON cases. The JSONC file was left unchanged and the snippet printed. `compose-preview-mcp` failed only because the CLI was not installed in that sandbox. |

Not verified: a real model choosing the subagent or acting on the reminder, and a render through
`compose-preview mcp serve` in OpenCode.

### 2026-09-27

Checked on 2026-09-27 with `opencode-ai@1.18.32` (the npm `latest`, OpenCode v1), Skills CLI 1.7.0 and `compose-preview` 2.28.0. No model or provider was configured, and each check ran in an empty `HOME`.

| Check | Command | Result |
| --- | --- | --- |
| Skills discovery | the `npx skills add … --global --yes` command above, then `opencode debug skill` | Both `compose-preview` and `compose-ui-builder` listed from `~/.agents/skills`. The same result with `--agent opencode`. |
| Local server config | `opencode mcp list` with the `mcp.servers.compose-preview-mcp` entry that `mcp install --opencode` writes, pointed at a stub stdio MCP server | Parsed and `connected`. OpenCode 1.18.32 also accepts the v1 `mcp.<name>` shape. |
| Remote catalog config | `opencode mcp list` with the `compose-preview-catalog` entry above and no token | `connected`. |
| Catalog OAuth discovery | `opencode mcp debug compose-preview-catalog` | Server `compose-preview-catalog` 3.77.0 answered `200 OK`, auth status `not authenticated`. The interactive `opencode mcp auth` browser flow was not exercised. |

A [2026-10-02 smoke run](https://github.com/yschimke/compose-agent-plugins/issues/77#issuecomment-5950589884) on OpenCode 1.18.32 with `compose-preview` 2.32.0 stopped at registration: the user config was `opencode.jsonc`, so `mcp install --opencode` printed the snippet, and the check then flagged v1 as unsupported. The check now accepts 1.18 and prints the snippet.

Not verified: OpenCode v2 (its installer host was unreachable from the test environment), a real `compose-preview mcp serve` session against a Gradle project, and tool calls through either server.
