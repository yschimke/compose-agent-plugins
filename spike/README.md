# Harness spike fixture

This fixture supports issue [#6](https://github.com/yschimke/compose-agent-plugins/issues/6) and [#52](https://github.com/yschimke/compose-agent-plugins/issues/52). It is deliberately separate from shipping plugins and makes no claim about a harness until that harness has run it.

The Antigravity root manifests follow the current official schema URL and omit
the older `version` field. Claude Code uses the adjacent `.claude-plugin`
manifest. Codex uses the `.codex-plugin` compatibility manifest, which points
at the fixture's `skills/` and `.codex-mcp.json` paths without competing with the
Antigravity root `plugin.json`.

## Prepare and verify the fixture

From the repository root:

```sh
python3 spike/prepare.py
python3 spike/run-protocol-smoke.py
```

`prepare.py` copies the echo MCP server and hook logger into each ignored
`spike/p*/echo-mcp/` directory, then writes ignored Antigravity `mcp_config.json`
and `hooks.json` files that point to that plugin-local copy. It is safe to run
after moving the checkout; do not install the Antigravity fixtures before
preparation.

The smoke test speaks JSON-RPC directly, confirms both servers expose the
deliberately colliding `render_preview`, `open_file`, `viewer_report`, and
`status` tools, and confirms that `render_preview` supplies a 1×1 PNG image. It
also verifies client capability logging (`extensions["io.modelcontextprotocol/ui"]`),
the MCP App resource and file-viewer probe UI, text fallbacks, `elicitation/create`,
and prompts. It is not evidence of any harness behaviour.

## Run in a harness

Install or enable both `p1` and `p2` using the harness-specific procedure under test. Then perform the question prompts from issue #6 and preserve the evidence:

- Inspect `/tmp/spike-*.json` for `clientInfo`, `protocolVersion`, `capabilities` (including `mcpAppsExtension` for `io.modelcontextprotocol/ui`), server-side `events` (`resources/list`, `resources/read`, `tools/call`), `viewerReports`, and environment variables (Q8, Q16–Q17).
- Inspect `/tmp/spike-hooks.log` after a file edit and at end of turn (Q3–Q4).
- Ask the harness to call `render_preview` on `beta` after both plugins are active (Q2 and Q10).
- Ask `spike check` and `rules check` to test discovery (Q6–Q7).
- Call `render_preview`, confirm its text fallback remains visible, then use
  the viewer button (`Send viewer action`) to probe its `tools/call` to `status`,
  `ui/message` postMessage bridge, and automatic report persistence via
  `viewer_report` (Q16–Q17).
- Open a `.uid` or `.rc` file (or call `open_file` with `{file: {name, resourceUri}}`)
  to probe MCP App file-viewer entrypoints, `resources/read`, `resources/subscribe`,
  host `_meta` path injection, and local file write-back (`openai/resources/write`
  and `resources/write` / `ui/resources/write` fallbacks).
- Call `ask` with both `mode: form` and `mode: url`; if no interaction appears,
  verify that form mode offers the `compact` and `expanded` choices in text,
  while URL mode supplies the authorization URL, verification code, and status
  polling instruction; call `access_status` to complete that fallback (Q18).
  List and get `spike-prompt` to probe prompts (Q19).
- Ask for the `spike-reviewer` fixture from plugin `p1` (Q20). In Claude Code
  and Codex, confirm the SessionStart hook both logs and prints
  `SPIKE-SESSION-START` so the model can be asked to repeat it (Q21).

The static marketplace fixture is at `.claude-plugin/marketplace.json`; the
same entries are also available as `.agents/plugins/marketplace.json` for
Codex marketplace resolution tests. Claude Code's `.mcp.json` starts the bundled
server from `${CLAUDE_PLUGIN_ROOT}/echo-mcp/server.py`, because Claude Code
resolves relative args against the session directory and ignores `cwd`. Codex's
`.codex-mcp.json` keeps package-relative `cwd: "."` until Codex expansion of
`${CLAUDE_PLUGIN_ROOT}` in `args` is confirmed; hook commands use
`CLAUDE_PLUGIN_ROOT`, which Codex also supplies for compatibility. The
Antigravity config is generated because variable expansion for command paths
is itself unverified.

## Antigravity v2.31+ MCP Apps and file-viewer runbook

Antigravity `v2.30.0` rolled out MCP Apps in the Side Panel `Extensions` tab,
and `v2.31.0` added local file save support for MCP App file viewers. Run the
interactive smoke helper on a desktop machine with Antigravity `v2.31.0+`:

```sh
python3 scripts/antigravity-mcp-apps-smoke.py
```

The helper runs `spike/prepare.py` and `spike/run-protocol-smoke.py`, stages
scratch `sample.uid` and `sample.rc` files in a temporary directory, prints the
exact `agy plugin install` and chat/editor steps, and summarizes the updated
`/tmp/spike-*.json` files after pressing Enter:

1. **Capabilities & Side Panel (`render_preview`)** — confirms whether
   `initialize` advertises `capabilities.extensions["io.modelcontextprotocol/ui"]`,
   whether Antigravity reads `ui://spike/app` and mounts it in Side Panel →
   `Extensions` (or inline), whether `ui/notifications/tool-input` and
   `ui/notifications/tool-result` fire, and whether `Send viewer action`
   completes `tools/call` + `ui/message`.
2. **File viewer & local save (`open_file`)** — probes `.uid` / `.rc` file
   entrypoint matching (`_meta["openai/ui"].entrypoints`), `resources/read`
   (`_meta`, `writable`, `etag`), `resources/subscribe`, server-side `_meta`
   local path injection on `viewer_report`, and two-step confirmed local file
   write-back (`openai/resources/write`, `resources/write`, `ui/resources/write`).
3. **Cleanup & evidence** — uninstall `p1` / `p2` (`agy plugin uninstall p1`),
   record observed outputs in `docs/evidence/`, and only then update
   `docs/harness-matrix.md`.

To summarize existing `/tmp/spike-*.json` files without rerunning the prompt:

```sh
python3 scripts/antigravity-mcp-apps-smoke.py --logs-dir /tmp
```

## Hook decisions

`hook-log.sh` only observes by default. Set `SPIKE_HOOK_DECISION=continue` or `SPIKE_HOOK_DECISION=block` before starting a harness to emit the corresponding candidate Stop decision and test Q4. This intentionally keeps fixture installation from blocking normal work.

## Rich-protocol fixture fallbacks

The echo server attaches `ui://spike/app` as `text/html;profile=mcp-app` to
`render_preview` and `open_file` through both `_meta.ui.resourceUri` and legacy
`_meta["ui/resourceUri"]`. Both tools always return text and a `resource_link`
as their fallback. The app performs the portable `ui/initialize` then
`ui/notifications/initialized` handshake, checks that messages came from
`window.parent`, handles JSON-RPC errors and host notifications
(`ui/notifications/tool-input`, `ui/notifications/tool-result`,
`ui/notifications/host-context-changed`, `notifications/resources/updated`),
persists its report to `/tmp/spike-*.json` through the app-only `viewer_report`
tool, and probes both `tools/call` + `ui/message` and local file read/write. It
is fixture code rather than an assertion that a host supports MCP Apps.

`ask` sends `elicitation/create` in both form and URL modes and reports a
complete text choice when a client declines or cannot support elicitation. It
uses MCP protocol `2025-11-25`, which supports URL mode. `prompts/list` and
`prompts/get` provide the `spike-prompt` probe. Plugin `p1` includes an
`agents/spike-reviewer.md` discovery fixture, and its SessionStart hook records
and prints the `SPIKE-SESSION-START` marker. Every result remains usable as
text.

The server sends form elicitation only after the client advertises
`elicitation.form` (or the legacy bare `elicitation: {}`), and URL elicitation
only after `elicitation.url`; otherwise `ask` returns the text fallback without
sending a server-to-client request.
