---
name: compose-preview-setup
description: Run right after the compose-preview plugin is installed, or when a render fails because the CLI is missing or the project is "not prepared". Checks the compose-preview CLI, prepares the current Gradle project once, and renders one preview so the person sees it working.
---

# Set up Compose Preview

This is the plugin's onboarding skill. Keep it short: a few commands, then one render. Report
each step in one line. Do not grep the source first.

Check that the canonical `compose-preview` and `compose-ui-builder` skills from
`yschimke/skills` (the default `compose-skills` bundle) are available. This
plugin supplies host wiring, not those workflows. If either is missing, report
it and point to the host's install instructions in
[host setup](https://github.com/yschimke/compose-agent-plugins/blob/main/docs/host-setup.md).
Continue the CLI/render checks that are available; do not claim design-to-code
onboarding is complete while the canonical skills are missing.

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
4. **Close** with one line on what to do next: ask for any preview by name ("render the
   `ListScreenPreview`"); in ChatGPT/Codex desktop the Previews tab and `@`-mentions of
   previews are available when the host shows them.

Never edit build files by hand, never run `./gradlew clean`, and never hand-build a mock of a
render.
