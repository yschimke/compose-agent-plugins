# Compose Preview

Iterate on local Jetpack Compose `@Preview` functions with live rendering and
accessibility checks. The plugin connects your agent to the `compose-preview`
command-line tool, which renders previews from your own Gradle project on your
machine.

Start at <https://ui.coo.ee/start>. This folder is generated from
[`yschimke/compose-agent-plugins`](https://github.com/yschimke/compose-agent-plugins);
install steps for each harness are in its
[host setup](https://github.com/yschimke/compose-agent-plugins/blob/main/docs/host-setup.md#install-per-host).

## Requirements

Java 17, a Gradle project with `@Preview` functions, and the `compose-preview`
CLI on `PATH`. Install the CLI with the
[setup guide](https://github.com/yschimke/skills/blob/main/skills/compose-preview/references/setup.md)
in `yschimke/skills`. The plugin does not download or install it.

## What it contains and runs

- An MCP server entry, `compose-preview-mcp`, that starts
  `compose-preview mcp serve` from your `PATH` over stdio. It builds and renders
  your project locally with Gradle.
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
- The `harness-notes` and `antigravity-viewer-card` skills, the
  `design-reviewer` agent, and the preview viewer bundle in `assets/`. The
  viewer is the unmodified `compose-preview-viewer.html` that compose-preview-mcp
  releases re-publish from compose-preview-server; its provenance file pins the
  tags and SHA-256.

For requested design reviews, install the canonical `compose-skills` bundle
from `yschimke/skills`. Its catalog guidelines checklist runs in every supported
harness, with the packaged reviewer when available or in the current context
otherwise. Rules remain in the catalogs. The reviewer preserves source and
design nodes and may record requested review metadata at a design's home.
See [review setup and fallbacks](https://github.com/yschimke/compose-agent-plugins/blob/main/docs/design-guidelines-review.md).

## Data it sends

Rendering runs on your machine. Gradle may download your project's own
dependencies, as any build of that project would. A keyless guidelines prompt
returns source, accessibility data and pictures to the agent's model. An
explicit provider check (`check_preview_guidelines` or the CLI's `guidelines`
command) sends that evidence and rules to OpenRouter using the configured key.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
