# Harness matrix

> Historical evidence below retains the repository and marketplace names used during the run.
> For current installation and migration instructions, see the
> [Compose Agent Plugins quick start](../README.md#quick-start).

This matrix records only observed results for the compatibility investigation in [issue #6](https://github.com/yschimke/compose-agent-plugins/issues/6). A blank result has not been inferred from documentation or another harness.

## Status for launch

A summary of the detailed rows below as of 2026-09-27. "…" means not yet
verified. Setup: [README quick start](../README.md#quick-start); fixes:
[troubleshooting](troubleshooting.md).

| Harness | Install | Render path | Card / UI | Hooks | Elicitation | Known gaps |
| --- | --- | --- | --- | --- | --- | --- |
| Antigravity (`agy` 1.2.12) | ✅ local path and GitHub `/tree/<ref>/<path>` URL (plugins are copied; reinstall to update) | ✅ one `render_preview` call, 53 s on a cold daemon | ✅ static card from the server `embed`; no MCP Apps | Stop and post-tool-use ✅; no SessionStart; Stop gate packaged (`hooks.json`), live block not yet run; `rules/AGENTS.md` packaged in place of SessionStart (loading shown by Q6; the product rules not yet run) | ❌ neither mode; text fallback | [#39](https://github.com/yschimke/compose-agent-plugins/issues/39): 30 s budget, Stop gate live run, grant flow |
| Claude Code (2.1.283) | ✅ GitHub marketplace | ✅ image reaches the model; `inline=false` + Read planned | Print mode only; no MCP Apps in CLI/IDE | ✅ SessionStart, PostToolUse, Stop (cap 9) | Form advertised; URL mode … | [#40](https://github.com/yschimke/compose-agent-plugins/issues/40): URL elicitation, plugin directory |
| Codex (0.157.1) | ✅ GitHub marketplace | ✅ Desktop: render, a11y/layout details, edit loop, compile-error recovery and `render_matrix` ([#76 run](https://github.com/yschimke/compose-agent-plugins/issues/76#issuecomment-5950380878)); `project` needed when the chat worktree is not the build | Desktop MCP App viewer ✅ shows; chooser, overlay toggle, variant sizing and matrix tiles failed on server 3.91.0 | Registered, `untrusted` until approved; behaviour … | Form ✅ shown; selection rejected ("Check this answer and try again") on server 3.91.0 | [#41](https://github.com/yschimke/compose-agent-plugins/issues/41): column gaps, no `design-reviewer`, MCP Apps |
| OpenCode (1.18.35) | ✅ skills via npx; server via `mcp install --opencode`; agent, rules skill and edit-reminder plugin via `opencode-install.py` | … | None (no MCP Apps) | Edit reminder ✅ plugin `tool.execute.after` (scripted model); no Stop veto | None | [#42](https://github.com/yschimke/compose-agent-plugins/issues/42): v2 and a real render unverified |
| Claude in Slack (Claude Tag) | … hosted `/mcp` as a connection (no local stdio server) | … signed https image link, attached or linked | None documented (text and attachments only) | None (plugins and skills via access bundle …) | Not documented; a thread reply is the answer | [#92](https://github.com/yschimke/compose-agent-plugins/issues/92): every cell, see [Chat surfaces](#chat-surfaces) |

## Fixture baseline

On 2026-09-26, `python3 spike/prepare.py && python3 spike/run-protocol-smoke.py` passed locally. The direct JSON-RPC client verified that both `alpha` and `beta` expose `render_preview` and `status`; `render_preview` returns a text item and a 1×1 PNG image. This establishes the fixture only, not host behaviour.

The fixture’s Antigravity `plugin.json` follows Google's
[official plugin manifest documentation](https://antigravity.google/docs/plugins#manifest-file-plugin-json):
the v1 schema URL, a required `name`, an optional `description`, and no `version` field. That differs
from the older issue text, which used `version`; the product scaffold follows the documented shape.
The documentation both recommends the `$schema` property and shows it in the canonical example,
although the full schema printed on that page omits `$schema` from `properties`. The vendored schema
keeps `$schema` as a constant so the documented example validates while a different schema URL does
not.

## Harness results

| Question | Antigravity | Claude Code | Codex | OpenCode | Evidence |
| --- | --- | --- | --- | --- | --- |
| Q1: Git subdirectory or marketplace installation | ✅ `agy` 1.2.12: local path and GitHub subdirectory URL | ✅ Claude Code 2.1.283: local path and GitHub marketplace | ✅ Codex 0.157.1: local path and GitHub marketplace | n/a | Claude Code: `claude plugin marketplace add` accepted the local `spike/` directory and `yschimke/compose-ag-plugin` (HTTPS clone, no prompt); `claude plugin install` installed both fixtures and both product plugins from their `./plugins/<name>` subdirectory sources. No `git-subdir` source was tested. [Claude Code evidence](evidence/2026-09-27-claude-code.md). Antigravity: `agy plugin install ./spike/p1` and `./spike/p2` installed from a local path and listed the skills, agents, commands, MCP servers and hooks processed; `agy plugin enable` printed nothing. [Antigravity evidence](evidence/2026-09-27-antigravity.md). `agy plugin install https://github.com/yschimke/compose-ag-plugin/tree/main/plugins/compose-preview` cloned the repository and installed that folder (3 skills, 1 agent, 1 MCP server, hooks); the bare repository URL installed only the root `gemini-extension.json` MCP servers. `plugin@marketplace` is advertised but not tried. [Antigravity git install evidence](evidence/2026-10-02-antigravity-git-install.md). Codex: `codex plugin marketplace add` accepted this checkout and `yschimke/compose-ag-plugin` (git clone) and read the existing `.claude-plugin/marketplace.json`; `codex plugin add` installed both product plugins from their `./plugins/<name>` sources, so `.agents/plugins/marketplace.json` is not needed. [Codex install evidence](evidence/2026-09-27-codex-install.md). |
| Q2: Duplicate MCP tool names | ✅ No clash in `agy` 1.2.12 | ✅ No clash in Claude Code 2.1.283 | Partial: both servers exposed in Codex 0.151.0 | Not run | With compatibility overlays and package-relative MCP working directories, both cached servers initialized. Direct calls to `alpha/status` and `beta/render_preview` completed, proving distinct server namespaces; the same colliding tool was not called on both servers. [Evidence](evidence/2026-09-26-codex-plugin-overlay.md). Claude Code: the model saw `mcp__plugin_p1_alpha__render_preview` and `mcp__plugin_p2_beta__render_preview` and called both. The fixture's `cwd: "."` server failed to start, so this ran with a temporary `${CLAUDE_PLUGIN_ROOT}` path overlay. [Claude Code evidence](evidence/2026-09-27-claude-code.md). Antigravity: servers are namespaced `<plugin>_<server>` (`p1_alpha`, `p2_beta`) and tools are called through a generic `call_mcp_tool(ServerName=…, ToolName=…)`. The product plugins followed the same pattern (`compose-catalogs_compose-preview-catalog`). [Antigravity evidence](evidence/2026-09-27-antigravity.md). |
| Q3: File-edit hooks and tool names | ✅ `agy` 1.2.12 | ✅ Claude Code 2.1.283 | Not run | ✅ OpenCode 1.18.35 (plugin hook) | OpenCode: a plugin's `tool.execute.after` received `write` with `args.filePath`, and text appended to `output.output` reached the model in the tool result; `apply_patch` takes `patchText` with `*** Add File:` / `*** Update File:` lines. Scripted model, [OpenCode verification record](opencode.md#verification-record). Claude Code: PostToolUse ran for each plugin after `Write` and after `Edit`; the log recorded `tool_name` `Write` and `Edit`. `MultiEdit` was not exercised. [Claude Code evidence](evidence/2026-09-27-claude-code.md). Antigravity: post-tool-use hooks fired for `write_to_file` and `replace_file_content`; the tool name is inside a `toolCall` object. [Antigravity evidence](evidence/2026-09-27-antigravity.md). |
| Q4: Stop-hook continuation or blocking | ✅ `agy` 1.2.12; no cap observed | ✅ Claude Code 2.1.283; cap 9 | Registered in Codex 0.157.1; behaviour not run | n/a | Claude Code: `{"decision":"block","reason":…}` from Stop fed the reason back as `Stop hook feedback` and the agent kept working. `stop_hook_active` was `false` on the first Stop, then `true`. The host overrode after "9 consecutive" blocks (configurable with `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`). [Claude Code evidence](evidence/2026-09-27-claude-code.md). Antigravity: `{"decision":"continue","reason":…}` from Stop kept the agent going ("Stop hook blocked termination: run spike check"). About 30 Stop events were logged with no host override before the owner stopped it. The payload has no `stop_hook_active`, and `executionNum` is not a re-entry counter, so an Antigravity Stop gate needs its own per-`conversationId` loop state. [Antigravity evidence](evidence/2026-09-27-antigravity.md). Codex: app-server `hooks/list` registered `compose-preview`'s Stop hook (`stop-gate.sh --harness=codex`, 360 s) with `trustStatus: untrusted`; no model turn ran, so continuation and any cap are unknown. [Codex install evidence](evidence/2026-09-27-codex-install.md). |
| Q5: Root `plugin.json` coexistence | ✅ `agy` 1.2.12 | ✅ Claude Code 2.1.283 | ✅ Codex 0.151.0 | n/a | A temporary `CODEX_HOME` installed both generated product plugins through the Claude-compatible marketplace while their directories also contained Antigravity v1 root manifests. Claude Code: `claude plugin validate` passed (warnings only) for both fixtures, both product plugins and both marketplaces while their directories also held the Antigravity root manifests and `.codex-plugin/`; installs also worked. Antigravity: `agy plugin validate ./spike/p1` reported nothing with `.claude-plugin/` and `.codex-plugin/` present. [Antigravity evidence](evidence/2026-09-27-antigravity.md). |
| Q6: `rules/AGENTS.md` discovery | ✅ `agy` 1.2.12 | Not loaded (not a Claude Code component) | Not run | n/a | Claude Code 2.1.283 answered `RULES-NONE` to `rules check`; plugin `rules/AGENTS.md` is not a Claude Code plugin component. Antigravity: `rules check` returned `RULES-P1-LOADED RULES-P2-LOADED`. [Antigravity evidence](evidence/2026-09-27-antigravity.md). |
| Q7: Skill discovery | ✅ `agy` 1.2.12 as `/spike-p1`, `/spike-p2` | ✅ Claude Code 2.1.283 as `p1:spike`, `p2:spike` | ✅ Codex exec 0.151.0 | Not run | The model loaded `spike-p1` and `spike-p2` by those names and returned both exact markers. [Evidence](evidence/2026-09-26-codex-rich-harness.md). Claude Code: skills were namespaced as `<plugin>:<skill directory>`, not by the frontmatter names `spike-p1`/`spike-p2`, and returned both markers. [Claude Code evidence](evidence/2026-09-27-claude-code.md). Antigravity: `spike check` returned `SPIKE-P1-LOADED SPIKE-P2-LOADED`; skills also appear as slash commands under their frontmatter names. [Antigravity evidence](evidence/2026-09-27-antigravity.md). |
| Q8: MCP client identity and environment | ✅ `agy` 1.2.12 (client identity, hook env) | ✅ Claude Code 2.1.283 | ✅ Codex 0.151.0 | Not run | Both servers recorded `clientInfo.name = codex-mcp-client`, title `Codex`, version `0.151.0`, and the environment keys visible to the server. [Evidence](evidence/2026-09-26-codex-plugin-overlay.md). Claude Code: `clientInfo.name = claude-code`, title `Claude Code`, version `2.1.283`; capabilities `elicitation: {}` and `roots.listChanged`. Server environment added `CLAUDECODE=1`, `CLAUDE_PLUGIN_ROOT`, `CLAUDE_PLUGIN_DATA` and `CLAUDE_PROJECT_DIR`. [Claude Code evidence](evidence/2026-09-27-claude-code.md). Antigravity: `clientInfo` `{"name":"antigravity-client","version":"v1.0.0"}`. Hook environment keys included `__CFBundleIdentifier`, `ANTIGRAVITY_CONVERSATION_ID`, `AGY_BROWSER_ACTIVE_PORT_FILE`, `AGY_BROWSER_WS_URL` and `CHROME_DEVTOOLS_MCP_JS`. The MCP server environment capture was empty. [Antigravity evidence](evidence/2026-09-27-antigravity.md). |
| Q9: Local PNG in Generative UI | ❌ Local file images do not render; `data:` and `https:` do | n/a | n/a | n/a | Antigravity: `<agent-embed>` renders the HTML file's content as an `iframe srcdoc` (`location.href` `about:srcdoc`, empty `hash` and `search`). Scripts run; `data:` and `https:` images render; `file:///` and relative images do not. There is no MCP Apps bridge. [Antigravity evidence](evidence/2026-09-27-antigravity.md). |
| Q10: MCP image rendering audience | ✅ `agy` 1.2.12: person and model | Partial: model ✅ for 64×64; 1×1 rejected | Partial: image result reached Codex 0.151.0 | Not run | `beta/render_preview` completed and the model observed its image item, text fallback, and `resource_link`; the noninteractive terminal did not establish how a person sees the image. [Evidence](evidence/2026-09-26-codex-plugin-overlay.md). Claude Code 2.1.283: the fixture's 1×1 PNG was removed with "an image in the conversation could not be processed" while its text and link still arrived; a 64×64 PNG reached the model, which reported its colour. The person-facing view was not observed in print mode. [Claude Code evidence](evidence/2026-09-27-claude-code.md). Antigravity: the `render_preview` ImageContent was shown to the person and reached the model, which described a Wear `ListScreenPreview` correctly; the host saved it as `media_0.png`. [Antigravity evidence](evidence/2026-09-27-antigravity.md). |
| Q11: Environment expansion in remote headers | Not run | ✅ Claude Code 2.1.283 | Partial: `env_http_headers` resolved in Codex 0.157.1; delivery not run | Not run | Claude Code: in a plugin `.mcp.json` HTTP server, `${VAR}`, `${VAR:-default}` and `${CLAUDE_PLUGIN_ROOT}` in `headers` all arrived expanded at a local echo. [Claude Code evidence](evidence/2026-09-27-claude-code.md). Codex: `codex mcp get compose-preview-catalog --json` showed `env_http_headers` mapping `X-Compose-Preview-Token` to the `COMPOSE_PREVIEW_TOKEN` key; the header reaching a server was not observed. [Codex install evidence](evidence/2026-09-27-codex-install.md). |
| Q12: Skiko/Wasm under Generative UI CSP | Not run | n/a | n/a | n/a | — |
| Q13: Existing `yschimke-skills` marketplace | n/a | Install ✅; trigger ✅ | Install ✅; trigger not run | n/a | Codex 0.151.0 added `yschimke/skills`, installed `yschimke-skills` 0.1.4, and cached all 8 `SKILL.md` files. No model turn tested triggering. Claude Code 2.1.283 added `yschimke/skills`, installed `yschimke-skills` 0.1.5 with 8 skills, and a Compose `@Preview` request loaded `yschimke-skills:compose-preview`. |
| Q14: Canonical skills from `~/.agents/skills` or Skills CLI | ❌ Skills CLI install not loaded by `agy` 1.2.12 | n/a | n/a | n/a | Antigravity: `npx skills add … --agent antigravity --global` (skills 1.7.0) installed to `~/.agents/skills/compose-preview`, but a new session did not list it. A copy in `~/.gemini/antigravity/skills` was not tested. [Antigravity evidence](evidence/2026-09-27-antigravity.md). |
| Q15: Canonical skills plus wiring plugins coexist | Not run | ✅ Claude Code 2.1.283 | Install/list ✅; trigger not run | Not run | Codex 0.151.0 enabled `yschimke-skills`, `compose-catalogs`, and `compose-preview` together. The wiring plugins contain only the shared `harness-notes` skill, so they introduced no duplicate canonical Compose skill IDs. Claude Code: with all three enabled, every skill and agent was plugin-namespaced (`yschimke-skills:*`, `compose-preview:harness-notes`, `compose-catalogs:harness-notes`), so no ID clashed; `design-reviewer` was listed once per wiring plugin; it now ships only in `compose-preview` (#34). |
| Q16: MCP App viewer resource rendering | ❌ Not rendered in `agy` 1.2.12 | Not rendered in print mode | Partial: resource link reached Codex 0.151.0 | Not run | `beta/render_preview` returned its image, text fallback, and `ui://spike/app` resource link, but `codex exec` did not open or render an MCP App surface for the person. [Evidence](evidence/2026-09-26-codex-plugin-overlay.md). Claude Code 2.1.283 `-p`: the resource link reached the model as text `[Resource link: Spike echo viewer] ui://spike/app`; the host ran `resources/list` but never `resources/read` for the viewer. The interactive UI was not run. Antigravity: the tool result showed the image and text only; the MCP App viewer resource was not rendered. [Antigravity evidence](evidence/2026-09-27-antigravity.md). |
| Q17: Viewer postMessage actions | n/a (no viewer) | Not run | Not run | Not run | The noninteractive probe did not open the viewer or invoke its bridge actions. Claude Code print mode opened no viewer, so its bridge could not be exercised. |
| Q18: `elicitation/create` | ❌ Neither form nor URL in `agy` 1.2.12 | Partial: `elicitation: {}` advertised; print mode fell back | Tool exposed; interaction not run | Not run | Both servers exposed `ask`, but this probe did not call either elicitation mode. Claude Code 2.1.283 advertised form-only elicitation. The fixture sent a form `elicitation/create`, print mode showed nothing, and the tool returned the text fallback; URL mode was not advertised and returned the URL/code fallback. The interactive UI was not run. Antigravity: both modes returned the fixture's text fallback. [Antigravity evidence](evidence/2026-09-27-antigravity.md). |
| Q19: `prompts/list` and `prompts/get` | ✅ Listed in `agy` 1.2.12; invocation not run | ✅ Claude Code 2.1.283 | Not run in interactive UI | Not run | Both MCP servers initialized, but the noninteractive probe did not exercise prompt discovery and has no slash-command picker; this is not a product-level negative result. Claude Code listed `/mcp__plugin_p1_alpha__spike-prompt` and the beta equivalent as slash commands after `prompts/list`; invoking one in `-p` sent `prompts/get` with `path: Example.kt`. [Claude Code evidence](evidence/2026-09-27-claude-code.md). Antigravity: prompts were listed as slash commands `mcp:p1_alpha:spike-prompt` and `mcp:p2_beta:spike-prompt`. [Antigravity evidence](evidence/2026-09-27-antigravity.md). |
| Q20: Plugin `agents/` reviewer discovery | ✅ `agy` 1.2.12 | ✅ Claude Code 2.1.283 | Blocked in Codex exec 0.151.0 | Discovery ✅ OpenCode 1.18.35 (`opencode agent list`); spawn not run | One session exposed no invocable `spike-reviewer`; in another, the prompt supplied the name and the attempted spawn failed. Neither run established packaged-agent discovery. [Evidence](evidence/2026-09-26-codex-rich-harness.md). Claude Code listed `p1:spike-reviewer` as an Agent type; spawning it returned the exact fixture verdict. [Claude Code evidence](evidence/2026-09-27-claude-code.md). Antigravity: "Use the spike-reviewer agent from p1" ran a subagent that returned the exact fixture verdict. [Antigravity evidence](evidence/2026-09-27-antigravity.md). |
| Q21: SessionStart hook marker | ❌ No SessionStart-equivalent event in `agy` 1.2.12 | ✅ Claude Code 2.1.283 | ✅ Codex exec 0.151.0 | n/a | Logs prove both plugin hooks ran with plugin-specific roots; a later run's model repeating their shared marker proves at least one output reached context. Both Stop observers also ran once. [Evidence](evidence/2026-09-26-codex-rich-harness.md). Claude Code: both SessionStart hooks ran with source `startup`; the model quoted `SessionStart:startup hook success: SPIKE-SESSION-START`. [Claude Code evidence](evidence/2026-09-27-claude-code.md). Antigravity: only Stop and post-tool-use hook events were logged. [Antigravity evidence](evidence/2026-09-27-antigravity.md). |
| Q22: Cross-repository marketplace entry (`git-subdir`) | n/a (installs by URL) | ✅ Claude Code 2.1.289 | ✅ Codex 0.160.0 | n/a | A local marketplace with one `{"source": "git-subdir", "url": "https://github.com/yschimke/skills.git", "path": "plugins/compose-skills"}` entry. Claude Code: `claude plugin validate` passed; `claude plugin marketplace add` and `claude plugin install compose-skills@<marketplace>` installed 0.1.8 at `yschimke/skills` 3ec4985 with both `SKILL.md` files. Codex: `codex plugin list` showed the source as the URL plus path; `codex plugin add` installed the same two skills. Cursor was not tried, so its marketplace keeps local plugins only. [Evidence](evidence/2026-10-04-cross-repo-marketplace.md). |

## Chat surfaces

Chat agents (Claude in Slack, also known as Claude Tag, and the ChatGPT Slack app) reach only the
hosted `/mcp`, and show a person text and attachments: no MCP Apps, viewer, editor, buttons or
elicitation, according to the Claude Tag docs summarised in
[compose-preview-server#1254](https://github.com/yschimke/compose-preview-server/issues/1254#issuecomment-5928444723).
The server side shipped in compose-preview-server
[#1258](https://github.com/yschimke/compose-preview-server/pull/1258) and
[#1264](https://github.com/yschimke/compose-preview-server/pull/1264): every hosted result that shows
a picture carries a signed https PNG link (an `Image: <url>` text line, `imageUrl`, and
`contactSheet.url` for a matrix); `ui_builder_get_links` reports `threadKind` and `slackThread`; and an
opt-in webhook posts comments, forks, decisions and implementation changes to a channel. Nothing below
has been observed yet; each cell stays "Not run" until it has been, under the rule at the top of this
page. The scripted checks (`chat_surfaces_smoke.py`) and the manual steps (B1–B9) are in
[compose-preview-server#1262](https://github.com/yschimke/compose-preview-server/issues/1262); those
checks need a deployment newer than 3.89.0.

| Question | Claude in Slack | ChatGPT Slack app | #1262 step |
| --- | --- | --- | --- |
| C1: Hosted `/mcp` as a connection (OAuth connector or Bearer) | Not run | Not run | B1 |
| C2: A signed https image from a tool result is attached or linked in the thread | Not run | Not run | B2, Part A |
| C3: MCP `ImageContent` from a tool reaches the model | Not run | Not run | B3 |
| C4: Pick by reply from a numbered contact sheet (`catalog_render_matrix`) | Not run | Not run | B4, B5 |
| C5: The agent recognises the design's Slack thread (`slackThread`) | Not run | Not run | B6 |
| C6: Comment summary stays at the home (R4) | Not run | Not run | B7 |
| C7: Plugins and skills from this repository load, and what they change | Not run | n/a | B8 |
| C8: PR-subscription follow-up | Not run | n/a | B9 |
| C9: Webhook notifications in a channel (rate limit, private designs) | Not run (operator check) | n/a | Operator check |

## Additional observations

- OpenCode 2.0.10 accepted two separately named local MCP server definitions in
  a temporary project config. No server startup, tool call, or model turn ran,
  so Q2 remains untested.
- Codex 0.151.0 installed both product plugins from this checkout as a local
  marketplace. Codex 0.157.1 (2026-09-27) also installed them from the
  `yschimke/compose-ag-plugin` GitHub marketplace, with no model session. Its
  app-server resolved, for `compose-catalogs`, the HTTP server
  `compose-preview-catalog` (initialized; 41 tools) and skill
  `compose-catalogs:harness-notes`; for `compose-preview`, the stdio server
  `compose-preview-mcp` (not started: no `compose-preview` CLI here), skills
  `compose-preview:harness-notes` and `compose-preview:antigravity-viewer-card`,
  and SessionStart and Stop hooks, both `untrusted` until approved. Neither
  plugin exposes `design-reviewer`: the Codex manifest has no agents entry.
  The Antigravity-only viewer-card skill is visible to Codex. See the
  [Codex install evidence](evidence/2026-09-27-codex-install.md).
- An earlier isolated Codex session, before the compatibility overlays and
  package-relative MCP working directories, loaded skills and hooks but no MCP
  servers. At plugin commit `dec6a63`, a fresh isolated install initialized
  both servers and completed approved `alpha/status` and
  `beta/render_preview` calls. This establishes Codex CLI transport, not MCP
  App presentation, elicitation, prompts, or packaged-agent discovery. See the
  [exact probe evidence](evidence/2026-09-26-codex-plugin-overlay.md).
- Claude Code 2.1.205 could not be exercised in an earlier environment: the
  minimal JSON prompt was killed with exit 137. Claude Code 2.1.283 ran on
  2026-09-27 in `claude -p` print mode with an isolated `CLAUDE_CONFIG_DIR`; its
  column records only that mode. Print mode has no viewer, picker or form, so
  its Q16–Q18 results are not product-level negatives. See the
  [Claude Code evidence](evidence/2026-09-27-claude-code.md).
- Claude Code 2.1.283 resolved the fixture's relative MCP argument
  `./echo-mcp/server.py` against the session directory, ignoring `cwd: "."`,
  so both fixture servers failed to connect as shipped. Package-relative
  servers need `${CLAUDE_PLUGIN_ROOT}` in `args` for Claude Code. The
  generated product plugins do not use a relative server path.
- Antigravity (`agy` CLI 1.2.12, Gemini 3.8 Flash High, macOS) was run by
  hand by the repository owner on 2026-09-27; its column records those
  observations only. Q11, Q12, Q15 and Q17 were not run. See the
  [Antigravity evidence](evidence/2026-09-27-antigravity.md).
- Antigravity results that change the plan: `<agent-embed>` cards are
  `iframe srcdoc` with no MCP Apps bridge and no `file:///` images, so a
  viewer card needs an inline result block or an `https` image route rather
  than a URL fragment; neither form nor URL elicitation is supported; no
  SessionStart-equivalent hook fired; the Stop `continue` decision had no
  observed cap and no re-entry flag; and the Skills CLI's `~/.agents/skills`
  install was not loaded. Plugin `rules/AGENTS.md`, skills and `agents/` all
  loaded, with MCP servers named `<plugin>_<server>` and skills as
  `/<frontmatter-name>`.
- With the product plugins in Antigravity, `compose-catalogs` rendered an M3
  Button, but its image arrived only as inline base64. To show it, the agent
  re-typed the base64 from its `brain/` session files into a PNG, which was
  costly (tracked in yschimke/compose-preview-server#1160). The
  `compose-preview` viewer-card skill made the agent print the PNG as base64
  and an unrendered `<agent-embed>` code block; #35 removes that behaviour.
- The current environment has no OpenCode executable. Its unrun cells stay
  explicit rather than inheriting results from another harness.

## Reproduction

Prepare the fixture, install both `spike/p1` and `spike/p2` with the harness-specific flow under test, then retain the command, harness version, prompt, and relevant `/tmp/spike-*.json` or `/tmp/spike-hooks.log` output with each completed cell. See [`spike/README.md`](../spike/README.md) for the fixture setup and prompts.
