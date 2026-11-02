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

## Verified with live grant (approved by @yschimke)

| Call | Result |
| --- | --- |
| `request_access` / `poll_access` (scope `live`) | Approved; token usable as tool `token` argument |
| `catalog_render_preview` `observe=png` for `compose-preview://catalog/wear-m3-catalog/alertdialog__ideal__edge-button__192dp` | PNG + text + signed `https://preview.coo.ee/mcp/render.png?…` resource returned |

Wear dialog with edge-button / check action rendered successfully in this Cloud
Agent session. MCP App empty-shell behaviour is an IDE/Cursor Desktop concern;
Cloud Agent chat receives the ordinary image/text tool result (R1).

## Reading

Cloud Agents can use hosted catalog tools when the HTTP MCP server is attached
in the agents dashboard. That is independent of the IDE plugin install. Live
PNG renders need the human access grant (`request_access` → approve →
`poll_access`), then pass the token on gated tools when the client cannot set
`X-Compose-Preview-Token`.
