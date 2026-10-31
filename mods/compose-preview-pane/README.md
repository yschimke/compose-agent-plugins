# compose-preview-pane (prototype)

A Claude Code [mod](https://code.claude.com/docs/en/changelog): a pane beside the chat that
shows the Compose previews of the Kotlin file Claude just edited, and the app running in the
`compose-preview launch` simulator. It closes the "no MCP Apps in the CLI or IDE" gap in the
[harness matrix](../../docs/harness-matrix.md#status-for-launch): the person sees the renders
without the model spending a turn or image tokens on them.

Status: a prototype. Its hooks validate, type-check and pass `claude plugin test`. The test
fixtures are payloads recorded from compose-preview CLI 2.77.0 and compose-preview-mcp 4.12.0
and 4.13.0
against [android/wear-os-samples](https://github.com/android/wear-os-samples) `ComposeStarter`.
The pane itself has not been watched in a live session yet. It is not in the marketplace yet.
The plan is to fold it into the `compose-preview` plugin.

## What it does

- **After every `Edit`, `Write` or `MultiEdit` of a `.kt` file** (debounced 250 ms), it renders
  the file's selected preview and shows it in the pane. No model turn is spent.
  - Over MCP: `find_previews_for_file`, `notify_file_changed`, then `render_preview {inline: false}`
    and `get_preview_data {kind: "a11y/atf"}` for the selected preview. The file's other previews
    keep their last picture, marked as from before the edit, and render when selected: the
    server renders one at a time, so rendering them all would queue ahead of the agent's own
    `render_preview`. It uses the warm daemon the
    `compose-preview` plugin already runs, called through `$.mcp.call`. A server that has not
    rendered the project yet maps no file to previews, so the mod first renders the file's first
    `@…Preview` function by name, then asks again.
  - Without an MCP server it falls back to the CLI: `compose-preview a11y --json --module <the
    edited file's module>`, run in the Gradle build that holds the file (the nearest
    `settings.gradle(.kts)`). It keeps only the rows whose `sourceFile` is the edited file. It
    does not use `show --with-extension a11y`, which drops the extension
    ([compose-ai-tools#6341](https://github.com/yschimke/compose-ai-tools/issues/6341)).
  - Multi-preview variants are labelled by function and variant, for example
    `GreetingScreenPreview · Devices - Large Round`.
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
  running app follows the code. It passes the Kotlin files edited since the last reload as
  `files`: compose-preview-mcp 4.14.0 compiles them in the warm preview build and reloads
  without Gradle (with CLI 2.79.0 or later), about 2 s from edit to pixels instead of 5 to 7. The simulator needs the MCP server; the CLI fallback covers
  renders only.

## Speed

The mod makes the agent's own renders faster, not only its own:

- **Warm-up on read.** The first time the agent reads a `.kt` file with `@…Preview` functions,
  the mod warms that project in the background: one render by name brings up the render
  daemon, and `notify_file_changed` for the unchanged file warms its in-process Kotlin compiler.
  The read is never delayed, and a warm-up that fails is tried again on the next read.
- **Compile on edit.** 250 ms after a Kotlin edit the mod sends `notify_file_changed`, even with
  the pane closed, so the compile is done, or under way, when the agent's `render_preview`
  arrives.

Both are speed only. A render that arrives while that compile runs waits for it, and a render
with no notice at all still compiles the edit itself, so neither can produce a stale picture.

Measured with compose-preview-mcp 4.13.0 on android/wear-os-samples `ComposeStarter`, 4 cores,
30 edit cycles over one MCP connection, replaying the mod's calls:

| Case | Agent's `render_preview` wait, p50 / p95 | Pane edit to pixels, p50 / p95 |
| --- | --- | --- |
| Agent renders 1.5 s after the edit | 0.36 s / 1.22 s | 1.67 s / 2.72 s |
| Burst of 3 edits | 0.40 s / 0.71 s | 1.64 s / 2.02 s |
| Agent renders 0.3 s after the edit | 1.41 s / 1.83 s | 1.71 s / 2.12 s |
| No notice (before this change) | about 1.5 s every time | |

All 30 renders were fresh, and the pane's and the agent's PNGs had the same sha256. The warm-up
took 21 s from a fully cold server, while the agent was still reading.

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

- compose-preview-mcp 4.12.0, the newest release, advertises only `compose/semantics` by
  default. `get_preview_data {kind: "a11y/atf"}` answers "kind not advertised", so over MCP
  the pane shows renders without findings and says so. The CLI fallback does have the findings.
- The Running app tab needs compose-preview-mcp 4.13.0 or later, which adds the `simulator_*`
  tools; its test uses payloads recorded from 4.13.0 running ComposeStarter. `simulator_launch`
  finds the Android SDK from the MCP server's working folder (its `local.properties`) or
  `ANDROID_HOME`. A server started outside the project can fail with "needs an Android SDK
  platform's android.jar"; start the session in the project folder.

- There is no pixel diff yet: Before/After switches between the two pictures. MCP
  `history_diff` could add one.
- The MCP payload shapes are read loosely (`parse.ts`), because only the documented
  fields of `find_previews_for_file`, `render_preview` and `get_preview_data` are relied on.
- You can't tap the screenshot itself: an `Svg` reports no click coordinates. Taps go by
  text instead.
