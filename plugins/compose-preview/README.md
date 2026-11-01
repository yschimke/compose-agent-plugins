# Compose Preview

Iterate on local Jetpack Compose `@Preview` functions with live rendering and
accessibility checks. The plugin connects your agent to the `compose-preview`
command-line tool, which renders previews from your own Gradle project on your
machine, and to the hosted Material 3 and Wear catalogs and UI Builder. It is
the one plugin a coding agent needs.

Start at <https://preview.coo.ee/start/>. This folder is generated from
[`yschimke/compose-agent-plugins`](https://github.com/yschimke/compose-agent-plugins);
install steps for each harness are in its
[host setup](https://github.com/yschimke/compose-agent-plugins/blob/main/docs/host-setup.md#install-per-host).

## Requirements

Java 17, a Gradle project with `@Preview` functions, and the `compose-preview`
CLI on `PATH`. Install the CLI with the
[setup guide](https://github.com/yschimke/skills/blob/main/skills/compose-preview/references/setup.md)
in `yschimke/skills`; the plugin's `compose-preview-setup` skill walks the agent
through it. The plugin does not download or install it. The hosted catalog
server needs none of this.

## What it contains and runs

- An MCP server entry, `compose-preview-mcp`, that starts
  `compose-preview mcp serve` from your `PATH` over stdio. It builds and renders
  your project locally with Gradle.
- An MCP server entry, `compose-preview-catalog`, for the hosted server at
  `https://preview.coo.ee/mcp` (Streamable HTTP): the Material 3 and Wear
  component catalogs and the UI Builder.
- The `compose-preview` and `compose-ui-builder` skills, copied unchanged from
  [`yschimke/skills`](https://github.com/yschimke/skills) at the commit recorded
  in this repository's `src/vendor/skills/provenance.json`, and the
  `compose-preview-setup` onboarding skill.
- A `SessionStart` hook, `scripts/session-start-summary.sh`, that asks the
  `compose-preview` CLI for its status and reports only fixed status words and
  counts.
- A `Stop` hook, `scripts/stop-gate.sh`, that does nothing unless you set
  `COMPOSE_PREVIEW_GATE=1`. When enabled, it runs `git`, `compose-preview show`
  and `compose-preview a11y` on previews in changed Kotlin files, and keeps the
  agent working only when one fails to render or has accessibility errors.
- A `PostToolUse` hook, `scripts/compose-edit-reminder.sh`, that adds one line
  asking for a render after the agent edits a Compose `*.kt` file. All three
  hooks are described in
  [hooks](https://github.com/yschimke/compose-agent-plugins/blob/main/docs/hooks.md).
- An Antigravity Auxiliary Pane sidecar, `sidecars/compose-preview/sidecar.json`
  (`sidecars/launch.mjs`), that lazily proxies `compose-preview browse`,
  `compose-preview ui-builder`, or `compose-preview launch --adb` (which also
  exposes `emulator-5554` + gRPC `8554` to `adb` and Android Device Hub).
- The `harness-notes` and `antigravity-viewer-card` skills, the
  `design-reviewer` agent, and the preview viewer bundle in `assets/`. The
  viewer is the unmodified `compose-preview-viewer.html` that compose-preview-mcp
  releases re-publish from compose-preview-server; its provenance file pins the
  tags and SHA-256.

For requested design reviews, the `compose-preview` skill's catalog guidelines
checklist runs in every supported harness, with the packaged reviewer when
available or in the current context otherwise. Pull request review and preview
CI are in the optional `compose-review` plugin. Rules remain in the catalogs. The reviewer preserves source and
design nodes and may record requested review metadata at a design's home.
See [review setup and fallbacks](https://github.com/yschimke/compose-agent-plugins/blob/main/docs/design-guidelines-review.md).

## Data it sends

Rendering your project runs on your machine. Gradle may download your project's own
dependencies, as any build of that project would. A keyless guidelines prompt
returns source, accessibility data and pictures to the agent's model. An
explicit provider check (`check_preview_guidelines` or the CLI's `guidelines`
command) sends that evidence and rules to OpenRouter using the configured key.

Every hosted catalog, render and UI Builder tool call goes to `preview.coo.ee`,
which the plugin author operates, with the tool arguments: component and preview
names, device settings, and any design document or comment text you ask the
agent to create or change there. Nothing is sent until the agent calls one of
those tools. The optional **Compose Preview token** is sent as the
`X-Compose-Preview-Token` header; in Claude Code you enter it when you enable
the plugin, and it is stored in the system credential store.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
