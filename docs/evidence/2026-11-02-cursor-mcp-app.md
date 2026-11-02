# Cursor MCP App empty viewer (2026-11-02)

## Observed

After installing the Cursor plugin and asking for a Wear Material 3
`EdgeButton` large-round catalog render, Cursor opened
`ui://compose-preview/viewer` inline. The iframe stayed on its default copy:

- meta: "Waiting for a preview result…"
- canvas: "This viewer displays render and matrix results when the host supplies them."

That is the shell HTML before any `ui/notifications/tool-result`. The hosted
catalog (compose-preview-server 3.154.0) does advertise
`_meta.ui.resourceUri: ui://compose-preview/viewer` on `catalog_render_preview`.

## Reading

Cursor mounts the MCP App resource from tool metadata. It does not always
deliver the matching tool result into the iframe over the MCP Apps bridge.
The image/text fallback in the ordinary tool result remains the R1 surface.

## Follow-up outside this repository

`compose-preview-server` `mcp-app/compose-preview-viewer.html`: after a
successful `ui/initialize`, if no tool result arrives within ~2.5s, replace the
waiting copy with an explicit "host opened the viewer without a tool result;
use the chat fallback" notice. A local commit was prepared on
`cursor/mcp-app-empty-result-notice-f16d` but this agent cannot push that
repository (403). Apply there, release, then sync the viewer asset here with
`scripts/update-viewer.py`.
