# Host setup notes

The per-host details that the generic skills in
[yschimke/skills](https://github.com/yschimke/skills) leave out. Those skills say what to do and
which tools to use; this page says how each agent host is wired up for them. It moved here from
yschimke/skills, which keeps a pointer at each place it was.

## Canonical workflow skills

Enable the default `compose-skills` bundle alongside this marketplace's host
plugins. Per-host installation commands are in the
[README](../README.md#install); Codex's `/plugins` lists `compose-skills` from
this marketplace, backed by `yschimke/skills`. Confirm both `compose-preview`
and `compose-ui-builder` are discoverable before calling design-to-code setup
complete. Do not add a second copy of the same skills from another marketplace.

## Registering the local MCP server

`compose-preview mcp install` registers the local MCP server with every agent host it detects,
after preparing the project. Use it when you are not using this repository's plugins; with the
`compose-preview` plugin installed, the plugin registers the server and `mcp install` must only
prepare the project (the `compose-preview-setup` skill passes the `--no-…` flags for that).

```bash
compose-preview mcp install                      # every detected host
compose-preview mcp install --antigravity        # force the Antigravity write
compose-preview mcp install --no-claude          # skip `claude mcp add`
compose-preview mcp install --codex              # force the Codex write
compose-preview mcp install --codex-config /path/to/config.toml
```

How each host is detected, and where its entry goes:

- **Claude Code**: `claude` on PATH, or `~/.claude/` exists. Registered via
  `claude mcp add --scope user` when missing; a broken entry is repaired in place and a healthy
  one is left alone.
- **Codex**: `codex` on PATH, or `~/.codex/` exists. The `[mcp_servers.compose-preview-mcp]`
  table is replaced in place (or appended) in `~/.codex/config.toml`.
- **Antigravity**: `__CFBundleIdentifier=com.google.antigravity`, `ANTIGRAVITY_CLI_ALIAS`, or
  `~/.gemini/antigravity/` exists. The entry is merged into
  `~/.gemini/antigravity/mcp_config.json`.
- **OpenCode**: see [OpenCode](opencode.md).

## Skill install locations

The skills' `compose-preview` stub runs from wherever the host installed the skill bundle:

- skills CLI (`npx skills add`): `~/.agents/skills/compose-preview/`
- Claude Code plugin from the `yschimke-skills` marketplace:
  `~/.claude/plugins/yschimke-skills/skills/compose-preview/`
- Claude Code and Codex plugins from this marketplace: under each host's plugin cache, for
  example `~/.claude/plugins/cache/compose-agent-plugins/compose-skills/<version>/skills/`.

## Cloud sandboxes

The portable setup (network allowlist, toolchain, bootstrap script, gotchas) is generic and stays
in the `compose-preview` skill's `references/agent-cloud.md`. Per host:

- **Claude Code on the web:** choose Custom network mode and include the trusted defaults. A
  proxy CA truststore is injected through `JAVA_TOOL_OPTIONS`, so match the `version "…"` line of
  `java -version`, never its first line.
- **Codex cloud containers:** ensure the outbound network policy allows the host list in
  `agent-cloud.md`; some environments default to restricted egress.
- **Gemini sandboxes:** verify the workspace policy includes the Google Maven and Gradle hosts;
  downloadable fonts often fail first when they are blocked.

For Claude Code, the setup script can also add user instructions that keep commits attributed
to the human. It appends a marked block to `~/.claude/CLAUDE.md`, leaving any instructions
already there in place, and does nothing when the block is already present:

```bash
mkdir -p ~/.claude && touch ~/.claude/CLAUDE.md
grep -q 'compose-agent-plugins: attribution' ~/.claude/CLAUDE.md || cat >> ~/.claude/CLAUDE.md <<'EOF'

<!-- compose-agent-plugins: attribution -->
## Commit attribution

- **Commits:** commit as the human. Author and Committer must not be an agent identity, and
  messages carry no AI `Co-authored-by:` or `Signed-off-by:` trailer. A `claude.ai/code`
  session link and a "Generated with" footer are fine: they record provenance, not authorship.
  Author and Committer come from `git config user.name` / `user.email`; if those look like an
  agent (`Claude`, `noreply@anthropic.com`, `*-bot@*`), stop and ask which human identity to use,
  then pass it explicitly with `git -c user.name='…' -c user.email='…' commit`. Do not commit
  under the agent identity and fix it afterwards.
- **PRs:** no agent named as author in titles or bodies.
- **Branches:** use `agent/...`, never `claude/...`. Rename a `claude/...` branch the harness
  hands you, and tell the user.
- **Cleanup:** before pushing or opening or editing a PR, check commits and PR text for an agent
  author, committer or co-author trailer, and offer to fix any you find.
EOF
```

## CI agent sessions

Mention-triggered sessions on a GitHub Actions runner: commenting `@claude <request>` on an issue
or PR (or applying a `claude` label) starts a Claude Code session through
`anthropics/claude-code-action`, configured in `.github/workflows/claude.yml`. The design is in
[compose-ai-tools `docs/AGENT_INVOCATION.md`](https://github.com/yschimke/compose-ai-tools/blob/main/docs/AGENT_INVOCATION.md).
What such a session should do differently (render with Gradle, push renders before linking them,
reuse CI's preview diff) is generic and stays in the `compose-preview-review` skill's
`references/ci-agent-sessions.md`.

What a `claude-code-action` session has, which that generic guide asks the session to check for
itself:

- **No `gh` CLI.** The action provides GitHub MCP tools for comments, reviews and CI status.
- **Push permission and a working branch.** The workflow's prompt grants pushing renders to the PR
  branch, or to the `agent/…` branch the action creates for an issue, and nowhere else.
- **A fresh run per mention.** Each `@claude` mention starts a new run that rereads the whole
  thread and the branch it pushed before; repeated mentions on a PR stack commits on that branch.
- **A narrow Bash allowlist**, typically `./gradlew` and read-only `git`, so the
  `compose-preview` CLI is often unavailable and renders go through the Gradle plugin.

### Expired hosted Compose Preview connection

In Codex/ChatGPT, explain the Compose Preview connection card's reconnect
action once. Stop repeated tool calls when it requires reauthentication. If
the person declines reconnecting, investigate source and deployment evidence
or continue local work without triggering another connection prompt. State
what a live confirmation would establish before requesting one.
If authorization instead says **Unknown client_id**, disconnect/remove the app
and add it again so the host performs dynamic client registration. A lost ID
cannot be recovered by retrying the same authorization URL. Server deployments
with durable OAuth client registration retain new IDs across restarts; grants
and approval sessions still require renewal. Other OAuth hosts follow the same
registration rule. For a reachable server's `authorization_required`, use the
advertised access-grant flow instead. Do not bootstrap a local environment or
clone the hosted catalog to recover either connection.


### Codex local design-to-code acceptance

Install the default `compose-skills` bundle as well as this marketplace's
`compose-preview` plugin. Codex loads its generated skill subset: harness
notes and onboarding. The Antigravity viewer-card skill remains packaged for
that host and is excluded from the Codex manifest's skill directory.

A real Codex acceptance run should open a checked-in `.uid` through the host's
file entrypoint, select a node, send a comment, edit the canonical document,
observe the editor reload, render against a reference, then change application
code and inspect its previews. Exercise a simultaneous user edit and resolve
the revision conflict without overwriting it. Record host/build, file revision,
render artifacts and each failed or unavailable capability. The UI Builder's
simulated MCP host tests prove protocol behavior; they do not prove this real
Codex flow or popup lifecycle. No real Codex acceptance run is recorded here.
