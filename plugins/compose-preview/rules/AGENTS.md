# Compose Preview

These rules load on every turn in hosts that read a plugin's `rules/` folder (Antigravity). The
workflows themselves are in the `compose-preview` and `compose-ui-builder` skills.

- **Render first.** To show or check a composable or `@Preview`, the first tool call is
  `render_preview` on the local `compose-preview-mcp` server with `preview=<FunctionName>` and
  `project=<absolute path of the open workspace>`. Always pass `project`: the server starts in the
  plugin folder and cannot find the workspace by itself. Don't search the project, read docs or
  list previews first. A miss names the closest matches; `pending` means call again with the same
  arguments.
- **Library components** (Material 3, Wear) come from the `compose-preview-catalog` server's
  `catalog_*` tools. Never write preview files into the person's project to show one.
- **After editing Compose UI**, render an affected preview and look at the PNG before calling the
  change done (R1). If rendering fails, say so with the error. Never hand-build a mock of a render.
- **Show it** with the `antigravity-viewer-card` skill: the `embed` line, a few bullets, no base64.
- **UI Builder designs:** before finishing work on one, run `compose-preview design status` once
  and report unacknowledged comments or unsaved temporary copies (R3, R4); this host has no
  session-start check that would.

Full contract: <https://github.com/yschimke/compose-agent-plugins/blob/main/docs/agent-rules.md>.
