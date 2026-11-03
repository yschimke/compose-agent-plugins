# Cursor MCP App empty-shell — upstream patch (2026-11-02)

## Why

Cursor often mounts `ui://compose-preview/viewer` from tool `_meta.ui.resourceUri`
without sending `ui/notifications/tool-result`. The bundled viewer then stays on
"Waiting for a preview result…" forever even when the chat already has the PNG
and text (R1 fallback). Recorded in
[2026-11-02-cursor-mcp-app.md](2026-11-02-cursor-mcp-app.md).

## Patch

Prepared against `yschimke/compose-preview-server` (local commit
`56a3588a031adf4befd2f96c3627d3cd5cdfa68b` on branch
`cursor/mcp-app-empty-result-notice-f16d`). This agent cannot push that
repository (403). The same diff is checked in as
[2026-11-02-compose-preview-viewer-empty-shell.patch](2026-11-02-compose-preview-viewer-empty-shell.patch).

After a successful MCP Apps bridge `ui/initialize`, wait ~2.5s; if no tool
result arrived, replace the waiting copy with an explicit chat-fallback notice.

## Apply (needs write access on compose-preview-server)

```sh
cd compose-preview-server
git checkout -b cursor/mcp-app-empty-result-notice
git apply path/to/compose-agent-plugins/docs/evidence/2026-11-02-compose-preview-viewer-empty-shell.patch
# open PR, release, then here:
python3 scripts/update-viewer.py <server-release-tag>
```

Do **not** hand-edit `src/assets/compose-preview-viewer.html` in this
repository; `scripts/update-viewer.py` is the only sync path.
