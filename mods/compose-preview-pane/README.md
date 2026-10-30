# compose-preview-pane (prototype)

A Claude Code [mod](https://code.claude.com/docs/en/changelog): a pane beside the chat that
shows the Compose previews of the Kotlin file Claude just edited, and the app running in the
`compose-preview launch` simulator. It closes the "no MCP Apps in the CLI or IDE" gap in the
[harness matrix](../../docs/harness-matrix.md#status-for-launch): the person sees the renders
without the model spending a turn or image tokens on them.

Status: a prototype. Its hooks validate, type-check and pass `claude plugin test` against mocked
MCP and CLI answers; it has not yet been run against a live `compose-preview mcp serve`.
It is not in the marketplace yet. The plan is to fold it into the `compose-preview` plugin.

## What it does

- **After every `Edit`, `Write` or `MultiEdit` of a `.kt` file** (debounced 700 ms), it renders
  that file's previews and shows them in the pane. No model turn is spent.
  - Over MCP: `find_previews_for_file`, then `render_preview {inline: false}` and
    `get_preview_data {kind: "a11y/atf"}` for each preview. It uses the warm daemon the
    `compose-preview` plugin already runs, called through `$.mcp.call`.
  - Without an MCP server it falls back to the CLI: `compose-preview show --json
    --with-extension a11y --module <the edited file's module>`, keeping only the rows whose
    `sourceFile` is the edited file.
- **Before and after.** It copies each preview's previous PNG aside before re-rendering, so the
  pane can switch between Before and After. A preview whose render did not change is marked
  "pixel-identical".
- **Accessibility findings** for the selected preview, with a toast when a render has ATF
  errors, and an **Ask Claude to fix these** button. The button fills the prompt with the
  findings; it does not send it.
- **It mirrors the agent's own calls.** When the model calls `render_preview` or any
  `simulator_*` tool, the pane shows that result too, so the person sees what Claude saw.
- **Running app tab** (`/compose-app [app.apk | project dir]`, or the pane's button). It starts
  the simulator through `simulator_launch` (headless, from the Gradle project by default) and
  shows a screenshot, with Back, Refresh, Reload edit, Restart and Stop buttons. A text field
  sends `tap {text}` (not on mobile, which has no input fields). After a Kotlin edit,
  a project-launched simulator runs `simulator_reload` and the screenshot refreshes, so the
  running app follows the code. The simulator needs the MCP server; the CLI fallback covers
  renders only.

Commands: `/preview-pane` opens the pane (named so it does not clash with the `compose-preview` skill); `/compose-app` opens it on the running app.

## Surfaces

The terminal draws PNGs with `Image` (kitty, Ghostty, iTerm2 3.5+). Desktop, VS Code and
mobile get the PNG inlined in an `Svg`, which caps a picture at about 96 KB; a larger one shows
its path instead.

## Options

| `userConfig` | Default | Meaning |
| --- | --- | --- |
| `mcp_server` | blank | The server name as `/mcp` lists it. Blank tries `plugin:compose-preview:compose-preview-mcp`, then `compose-preview-mcp`, then the CLI. |
| `max_previews` | 6 | How many previews of the edited file to render after each edit. |

## Run it from this checkout

For one session:

```bash
claude --plugin-dir mods/compose-preview-pane
```

Check it:

```bash
claude plugin validate mods/compose-preview-pane
```

```bash
claude plugin test mods/compose-preview-pane
```

## Known gaps

- There is no pixel diff yet: Before/After switches between the two pictures. MCP
  `history_diff` could add one.
- The MCP payload shapes are read loosely (`parse.ts`), because only the documented
  fields of `find_previews_for_file`, `render_preview` and `get_preview_data` are relied on.
- You can't tap the screenshot itself: an `Svg` reports no click coordinates. Taps go by
  text instead.
