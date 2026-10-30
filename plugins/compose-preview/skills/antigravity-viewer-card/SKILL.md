---
name: antigravity-viewer-card
description: Show a render of the person's own Compose previews in Antigravity — one render_preview call with preview=<FunctionName> on the local compose-preview-mcp server, a look at the PNG, then the card and a few bullets.
---

# Rendering previews in Antigravity

**Render first, explore later.** Your first tool call is `render_preview`.
Only if it fails do you look anything up.

1. Call `render_preview` on the **local** `compose-preview-mcp` server with
   `preview` set to the preview function name and `project` set to the
   absolute path of the open workspace, for example
   `preview: "ListScreenPreview", project: "/Users/me/workspace/MyApp"`.
   Always pass `project`: Antigravity starts the server in the plugin folder,
   so it can't find the workspace on its own. If the person names a screen
   rather than a preview (`ListScreen`), use `ListScreenPreview`. Nothing else
   is needed first: the server finds the preview and writes the card.
   Never use the `compose-preview-catalog` server for project previews: it
   only holds library catalogs.
   - If the result is `pending`, call `render_preview` again with the same
     arguments; the first render of a session waits for a Gradle build.
   - If the error names a `Closest` match that is clearly the preview the
     person meant, call once more with that name.
2. Look at the PNG at `pngPath` with the file viewer, so you see what the
   person sees (R1).
3. Reply with the `embed` line from the result, 2–4 bullets describing what
   you saw, and this summary, filled **only** from the result. Write
   "unavailable" for anything missing; don't look it up.

   ```text
   Render: <uri>
   Image: <widthPx> × <heightPx>; hash <sha256>
   ```

   Under it, add `[Open full size](file://<pngPath>)` so the person can see
   the PNG at its real size; the card fits it into a small frame.

   If the result lists `otherMatches`, name them in one line.

**After editing a preview's source**, call `render_preview` with the same
`preview` again; the server recompiles. Never run `./gradlew`, clean, or delete
build folders. If the image still shows the old code, call `render_preview`
once more with `force: {"reason": "<what you edited>"}`; if it is still stale,
say so and stop.

**Token-frugal iteration.** For intermediate checks before the final visual
sign-off, pass `observe: "semantics"` (default) or `observe: "hash"` to avoid
repeated full-screen PNG payloads, or pass `crop: {"ref": "n3"}` (or `testTag` /
`role` + `text`) with `observe: "png"` to inspect a single node's pixels. Always
inspect the rendered PNG (`observe: "png"` or `pngPath`) before calling a visual
change done (R1).

## Compose Preview Sidecar & App Simulator

The `compose-preview` plugin ships an Antigravity Auxiliary Pane sidecar with
three interactive modes (`browse`, `ui-builder`, and `simulator` via
`compose-preview launch --adb`). Surface a one-click pill in chat when the
person wants an interactive gallery, the local UI Builder, or a live
interactive app simulator:

- Open [Compose Preview](sidecar://compose-preview/compose-preview/) in the side
  pane to browse all `@Preview`s live, switch to the local UI Builder, or run
  `compose-preview launch --adb` in the browser simulator.
- When `Simulator (launch --adb)` is active in the sidecar (or started from the
  CLI with `compose-preview launch --project <dir> --live --adb`), it registers
  `emulator-5554` + gRPC `8554` with `adb`, so the person can also mirror and
  control the running app in [Android Device Hub](sidecar://android-cli-plugin/device-hub/)
  if `android-cli-plugin` is installed.

**Never fake a render.** Don't hand-build HTML, CSS, SVG or any other mock
of the preview, and don't draw it from the source. Only the PNG and card
from `render_preview` count as a preview. If rendering fails, say so, include
the error, and stop.

That's the whole task. Don't read other skill, asset or source files, search
the session or `brain/` folders, call `status`, `register_project` or
`list_previews` first, or print base64.

**Older servers** (the result has `pngPath` but no `embed`): run
`python3 ~/.gemini/config/plugins/compose-preview/assets/compose-preview-card.py '<result JSON text>'`
and use the line it prints. If `preview` is rejected, call `list_previews`
once, then `render_preview` with the `uri` and `inline=false`.

**Without the MCP server** (`compose-preview-mcp` is not enabled, not listed,
or not allowed in this context), run the same flow through the CLI from the
workspace folder; never switch to the `compose-preview-catalog` server:

1. `compose-preview show --preview <FunctionName> --json`, or, when the person
   asks about accessibility, `compose-preview a11y --preview <FunctionName> --json`
   (it renders too). Narrow to one preview; a miss lists the closest names.
2. Look at the PNG at the preview's `pngPath` (R1).
3. Run `python3 ~/.gemini/config/plugins/compose-preview/assets/compose-preview-card.py '<that JSON>'`
   and reply with the line it prints, the bullets and the summary as above
   (`Render: <id>`). An `a11y` run gives the card the same findings, overlay and
   Audit view; layout bounds need the MCP server, so say they are unavailable
   rather than describing them.

When the person asks about accessibility or layout, add
`details: ["a11y"]`, `["layout"]` or both to that same `render_preview` call:
the card gains the overlay toggles and the result one summary line each. Don't
call separate a11y or layout tools for it.

Do more (variants, source locations) only when the person asks.
