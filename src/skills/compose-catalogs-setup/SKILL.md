---
name: compose-catalogs-setup
description: Run right after the compose-catalogs plugin is installed, or when the hosted catalog server cannot be reached or asks for access. Checks the hosted preview.coo.ee catalog server, completes the access grant, and shows one catalog so the person sees it working.
---

# Set up Compose Catalogs

This is the plugin's onboarding skill. It needs no local toolchain. Keep it to a few tool calls
and report each step in one line.

1. **Reach the server.** Call `list_projects` on the `compose-preview-catalog` server once; it lists
   the catalogs.
   If the server is unreachable, say so with the error text and stop; do not retry in a loop.
2. **Access.** Distinguish the host connection from server access:
   - If the host reports an expired Compose Preview connection, show its reconnect action
     and stop tool retries. If the authorization page reports an unknown `client_id`, tell
     the person that reinstalling a marketplace plugin may retain the same rejected ID.
     The operator must restore its trusted registration, or the host must create a fresh
     app/registration. A changed app ID also needs updated plugin manifests; use the
     marketplace recovery steps in the host setup notes. Neither repeating that link
     nor `request_access` repairs a missing registration.
   - Only a reachable server's `authorization_required` response starts the grant flow below.
     A network/proxy error alone does not establish that a grant expired.
   - Do not clone catalogs, start Gradle or provision a cloud environment for this hosted flow.
   If the server asks for access:
   - Where the host supports URL elicitation, follow the access link it opens.
   - Otherwise use the text fallback: call `request_access`, show the person the link it returns,
     then call `poll_access` once they say they have approved it.
   - A `COMPOSE_PREVIEW_TOKEN` set in the plugin settings or the environment skips this step.
3. **First catalog.** Name the catalogs in one line (for example Material 3 and Wear). Pick one
   small component with `catalog_list_previews`, render it with `catalog_render_preview`, and
   describe it in a line.
4. **Close** with one line: ask for any component by name ("show the Wear `Button` variants"),
   or open the catalog from the sidebar where the host shows it.
