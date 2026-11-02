# Cursor Cloud Agent — catalog MCP (2026-11-02)

## Environment

Cloud Agent run on `yschimke/compose-agent-plugins` with the hosted
`compose-preview` / `compose-preview-catalog` MCP namespace attached (dashboard /
team MCP path, not `~/.cursor/plugins/local`).

## Verified without a live grant

| Call | Result |
| --- | --- |
| `status` | `toolCatalog.status: ready`; origin `https://preview.coo.ee`; catalogs loading/ready |
| `catalog_list_projects` | Dozens of remote catalogs including `wear-m3-catalog`, `m3-catalog` |
| `catalog_list_previews` (`wear-m3-catalog`) | Preview URIs returned (truncated page) |

## Needs live grant

`catalog_render_preview` with `observe=png` for
`compose-preview://catalog/wear-m3-catalog/alertdialog__ideal__edge-button__192dp`
answered that the published snapshot is unavailable and live scope is required.
`request_access` (scope `live`) was started; approve at the printed
`approveUrl` / `userCode`, then `poll_access` → pass `token` on render.

## Reading

Cloud Agents can use hosted catalog tools when the HTTP MCP server is attached
in the agents dashboard. That is independent of the IDE plugin install. Live
renders still need the same human access grant as other hosts.
