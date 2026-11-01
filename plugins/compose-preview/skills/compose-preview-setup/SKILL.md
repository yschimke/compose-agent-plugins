---
name: compose-preview-setup
description: Run right after the compose-preview plugin is installed, or when a render fails because the CLI is missing or the project is "not prepared". Checks the compose-preview CLI, prepares the current Gradle project once, and renders one preview so the person sees it working.
---

# Set up Compose Preview

This is the plugin's onboarding skill. Keep it short: a few commands, then one render. Report
each step in one line. Do not grep the source first. Open by pointing the person at
<https://preview.coo.ee/start/>.

This plugin ships the `compose-preview` and `compose-ui-builder` skills and both MCP servers
(the local `compose-preview-mcp` and the hosted `compose-preview-catalog`), so there is nothing
else to install.

**Only the UI Builder or the library catalogs?** If the CLI or Java is missing and the person
only wants to design in the UI Builder or browse the Material 3 and Wear catalogs, don't push a
JDK install: the hosted `compose-preview-catalog` server in this plugin already works. Call its
`catalog_list_projects` once to show it, and stop.

1. **CLI.** Run `compose-preview --version`.
   - If it is missing, tell the person and offer the installer. Run it only once they agree:
     `curl -fsSL https://raw.githubusercontent.com/yschimke/skills/main/scripts/install.sh | bash -s -- --cli-only`
     Then rerun `compose-preview --version`. If it is still not found, say a new terminal or
     restart of the app is needed, and stop here.
   - It needs Java 17 or newer. If the version check reports a Java error, say so and stop.
2. **Project.** Only if the workspace root has `settings.gradle.kts`, `settings.gradle` or
   `gradlew`; otherwise say there is no Gradle project open and stop after step 1.
   - Run `compose-preview mcp doctor --json` and read `verdict`.
   - If the verdict is not `ok`, prepare the project once:
     `compose-preview mcp install --no-claude --no-codex --no-antigravity --no-opencode --no-plugin-hint`
     The flags matter: this plugin already provides the MCP server, so `mcp install` must only
     prepare the project, never register a second global server.
   - "SDK location not found" means `ANDROID_HOME` or `sdk.dir` in `local.properties` is
     missing. Say which, and stop.
3. **First render.** Pick one preview function name: one the person named, or, since nobody has
   yet, one found with a single search for `@Preview` in `*.kt` files (prefer a name ending in
   `Preview` near the app's main screen). Call `render_preview` with `preview` set to that name and
   `project` set to the workspace's absolute path. The local server has no `list_previews` tool; if
   the name misses, its error lists the `Closest` matches, so retry once with the right one. A
   `pending` result means the project is still starting: call again with the same arguments. Look
   at the image and describe it in one or two lines. A failed render is reported as failed, with
   its error text.
4. **Close** with one line: ask for any preview by name ("render the `ListScreenPreview`"); in
   Antigravity, [Compose Preview](sidecar://compose-preview/compose-preview/) opens the Auxiliary
   Pane gallery, local UI Builder and live app simulator. Then, only after a successful render,
   at most three "what next" bullets:
   - PR previews in CI: the optional `compose-review` plugin
     (`/plugin install compose-review@compose-agent-plugins` in Claude Code) sets up CI that
     posts before/after renders on pull requests.
   - Designing a new screen: <https://ui.coo.ee/start>.
   - Browsing every preview yourself: `compose-preview browse`, or the VS Code extension.

Never edit build files by hand, never run `./gradlew clean`, and never hand-build a mock of a
render.
