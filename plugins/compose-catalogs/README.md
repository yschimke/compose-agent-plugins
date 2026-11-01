# Compose Catalogs

Discover Jetpack Compose components, inspect their properties, and render
catalog variants. The plugin connects your agent to the hosted Compose Preview
MCP service, which serves the Material 3 and Wear OS component catalogs and the
UI Builder design tools. It needs no local toolchain: use it on hosts with no
shell or Java (Claude chat and Cowork, ChatGPT, a UI Builder user without a
JDK). On a coding agent, install `compose-preview` instead; it carries the same
hosted server, so don't install both.

Start at <https://ui.coo.ee/start>. This folder is generated from
[`yschimke/compose-agent-plugins`](https://github.com/yschimke/compose-agent-plugins);
install steps for each harness are in its
[host setup](https://github.com/yschimke/compose-agent-plugins/blob/main/docs/host-setup.md#install-per-host).

## What it contains

- An MCP server entry, `compose-preview-catalog`, for the remote server at
  `https://preview.coo.ee/mcp` (Streamable HTTP). `https://ui.coo.ee/mcp` is
  the same server: don't configure it as well
  ([why](https://github.com/yschimke/compose-agent-plugins/blob/main/docs/host-setup.md#local-and-hosted-mcp-servers)).
- The registered Compose Preview app for Codex and ChatGPT. Its in-chat viewer
  shows preview-server renders and review controls; the full UI Builder remains
  the separate editor linked from that viewer.
- The `compose-ui-builder` skill, copied unchanged from
  [`yschimke/skills`](https://github.com/yschimke/skills), and the
  `compose-catalogs-setup` onboarding skill.
- The `harness-notes` skill, which summarizes the
  [agent rules](https://github.com/yschimke/compose-agent-plugins/blob/main/docs/agent-rules.md)
  for the active harness.
- No agents. The `design-reviewer` agent ships in `compose-preview`.

It has no hooks and runs no local programs.

For requested guidelines reviews, the `compose-ui-builder` skill's checklist
works with this plugin alone, in the current context when no reviewer agent is
available. Read published
`guidelines/result` products or judge an advertised keyless UI Builder prompt;
record requested review metadata at the design's home where permitted.
See [review setup and fallbacks](https://github.com/yschimke/compose-agent-plugins/blob/main/docs/design-guidelines-review.md).

## Data it sends

Every catalog, render and UI Builder tool call goes to `preview.coo.ee`, which
the plugin author operates. A call carries the tool arguments: component and
preview names, device settings, and any design document or comment text you ask
the agent to create or change there. Nothing is sent until the agent calls one
of those tools.

The optional **Compose Preview token** is sent as the `X-Compose-Preview-Token`
header. In Claude Code you enter it when you enable the plugin; it is stored in
the system credential store. Leave it blank to use the service's interactive
access grant instead.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
