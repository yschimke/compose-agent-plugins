# Host setup

The one page for wiring each agent host (Antigravity, Claude Code, Codex, OpenCode) to the
Compose preview tools. People new to the tools should start at <https://yschimke.github.io/compose-ai-tools/> (CLI and project previews) or <https://ui.coo.ee/start> (UI
Builder agent flow). The
generic skills in [yschimke/skills](https://github.com/yschimke/skills) say what to do and which
tools to use; this page says how each host is wired up for them. Installing and updating the
`compose-preview` CLI and the skills themselves is owned by the skills'
[setup guide](https://github.com/yschimke/skills/blob/main/skills/compose-preview/references/setup.md),
and MCP tool usage by its
[MCP reference](https://github.com/yschimke/skills/blob/main/skills/compose-preview/references/mcp.md).

## Local and hosted MCP servers

There are two different MCP servers, and most setups use both:

| | Local `compose-preview-mcp` | Hosted `compose-preview-catalog` |
| --- | --- | --- |
| Renders | Your own project's `@Preview`s, on your machine | The Material 3 and Wear catalogs, and UI Builder designs |
| Runs as | `compose-preview mcp serve` from the CLI, over stdio | Streamable HTTP at `https://preview.coo.ee/mcp` |
| Needs | Java 17, a Gradle project, the CLI on `PATH`, and the project prepared once | Nothing local; an access grant or the optional [token](distribution.md#the-compose-preview-token) |
| Plugin | `compose-preview` | `compose-catalogs` |

**Configure the hosted server as `https://preview.coo.ee/mcp`, and only that.**
`https://ui.coo.ee/mcp` is an alias of the same server process: same tools, same catalogs.
Access tokens are stored per origin, so configuring both gives every tool twice and two separate
access grants. If a host already has a `ui.coo.ee/mcp` entry, replace it rather than adding a
second one. `https://ui.coo.ee/start` is the UI Builder start page for people, not an MCP endpoint.

## Canonical workflow skills

Enable the default `compose-skills` bundle (`compose-preview`, `compose-ui-builder`) alongside
this marketplace's host plugins, using the per-host commands below. Confirm both skills are
discoverable before calling design-to-code setup complete. Keep one copy: a second copy from
another marketplace, or a `~/.claude/skills/compose-preview` link next to the plugin, loads each
skill twice (see [skill install locations](#skill-install-locations)). The wiring plugins do not
install the canonical skills.

## Install per host

Every host needs the CLI first for local rendering (see the
[setup guide](https://github.com/yschimke/skills/blob/main/skills/compose-preview/references/setup.md));
`compose-catalogs` alone needs nothing local. Each Compose project is then prepared once: the
plugin's `compose-preview-setup` skill does it, or see
[registering the local MCP server](#registering-the-local-mcp-server). Then open the project and
ask: **"render the `ListScreenPreview`"** (one of your own preview names).

### Antigravity

```sh
curl -fsSL https://raw.githubusercontent.com/yschimke/compose-agent-plugins/main/scripts/antigravity-install.py | python3 - --catalogs
```

The script installs `compose-skills` from yschimke/skills and `compose-preview` (plus
`compose-catalogs` with `--catalogs`) as plugins. It also updates an existing install,
uninstalling first (including a stale MCP-only `compose-preview`), and stops old
`compose-preview mcp serve` processes. `--dry-run` prints the commands only. By hand:

```sh
agy plugin install https://github.com/yschimke/skills/tree/main/plugins/compose-skills
agy plugin install https://github.com/yschimke/compose-agent-plugins/tree/main/plugins/compose-preview
agy plugin enable compose-preview
agy plugin install https://github.com/yschimke/compose-agent-plugins/tree/main/plugins/compose-catalogs   # optional
```

- Use the `/tree/main/plugins/<name>` URL: `agy` clones the repository and installs that folder.
  The bare repository URL installs only the two MCP servers from the root
  `gemini-extension.json` (no skills, agents or hooks) under the same `compose-preview` name.
- A local checkout works too (`agy plugin install ./compose-agent-plugins/plugins/compose-preview`),
  and `python3 scripts/antigravity-check.py` from a clone verifies the install.
- Install the skills as plugins, not with `npx skills add … --agent antigravity`: Antigravity
  1.2.12 does not load `~/.agents/skills` (issue #6 Q14). Add `compose-review-skills` or
  `compose-design-skills` from the same `/tree/main/plugins/<name>` path when you need them. The
  bare `yschimke/skills` URL installs all eight skills as `yschimke-skills`; don't keep it next to
  a bundle.

### Claude Code

```text
/plugin marketplace add yschimke/compose-agent-plugins
/plugin install compose-skills@compose-agent-plugins
/plugin install compose-preview@compose-agent-plugins
/plugin install compose-catalogs@compose-agent-plugins
```

The marketplace lists the canonical skill bundles and installs them straight from
yschimke/skills (`compose-skills`, and optionally `compose-review-skills` and
`compose-design-skills`). If you installed them earlier from the `yschimke-skills` marketplace,
uninstall that copy. Verify: restart, then `/mcp` lists
`plugin:compose-preview:compose-preview-mcp` as connected. Enabling `compose-catalogs` asks for
an optional Compose Preview token; Claude Code does not read `COMPOSE_PREVIEW_TOKEN` from the
environment.

### Codex

```sh
codex plugin marketplace add yschimke/compose-agent-plugins
# Then enable compose-skills, compose-preview and compose-catalogs from /plugins.
```

`compose-skills` comes from yschimke/skills through this marketplace; drop a separate
`yschimke/skills` marketplace if you added one before. In Codex and ChatGPT, `compose-catalogs`
also declares the registered Compose Preview app, which hosts the preview and review surface; the
full UI Builder stays in its own editor. Verify: `codex mcp list` shows `compose-preview-mcp` and
`compose-preview-catalog`. Approve the plugin hooks when Codex marks them untrusted.

### OpenCode

OpenCode has no plugin marketplace. From the Compose project root:

```sh
npx skills add yschimke/skills --global --yes --skill compose-preview --skill compose-ui-builder
curl -fsSL https://raw.githubusercontent.com/yschimke/compose-agent-plugins/main/scripts/opencode-install.py | python3 -
compose-preview mcp install --opencode
```

What the installer copies, the hand-written config, authentication and the check script are in
[OpenCode](opencode.md).

## Updating

- The CLI and npx-installed skills: see the
  [setup guide](https://github.com/yschimke/skills/blob/main/skills/compose-preview/references/setup.md).
- Claude Code and Codex: update the marketplaces and plugins from `/plugin` or `/plugins`.
- Antigravity copies plugins at install time, and installing over an existing plugin keeps its
  old record in `agy plugin list`. Rerun the [install script](#antigravity), or
  `agy plugin uninstall <name>` and then its `agy plugin install` line.
- OpenCode: rerun `opencode-install.py`.
- If renders look out of date after an update, clear the server cache
  (`rm -rf ~/.cache/composeai/preview-mcp`) and restart the harness. This is needed until
  yschimke/compose-ai-tools#5602 ships.

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
- [coo.ee/env](https://github.com/yschimke/coo-ee-env)'s `compose` and `skills` modules: a symlink
  in `~/.claude/skills/`, plus `~/.agents/skills/` when Codex or Gemini is on the box.

Keep one route per host. A host that has both the `compose-skills` plugin and a
`~/.claude/skills/compose-preview` link loads the skill twice.

## Cloud sandboxes

The portable setup (network allowlist, toolchain, bootstrap script, gotchas) is generic and stays
in the `compose-preview` skill's `references/agent-cloud.md`. Its setup line,
`curl -fsSL https://env.coo.ee/compose | bash`, works in every host below and prints any blocked
host it needs. Per host:

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

## Expired hosted Compose Preview connection

In Codex/ChatGPT, explain the Compose Preview connection card's reconnect
action once. Stop repeated tool calls when it requires reauthentication. If
the person declines reconnecting, investigate source and deployment evidence
or continue local work without triggering another connection prompt. State
what a live confirmation would establish before requesting one.
If authorization instead says **Unknown or expired client_id**, the server
has no current registration for the ID the host sends. Retrying the same URL
cannot repair it. Disconnecting/reinstalling a marketplace plugin can retain
its hosted app and OAuth client ID; do not promise that it forces registration.
For a reachable server's `authorization_required`, use the advertised
access-grant flow instead. Do not bootstrap a local environment or clone the
hosted catalog to recover either connection.

### Repairing a marketplace app registration

The `compose-catalogs` plugin references a hosted app through
`src/plugins.json` (`apps.compose-preview-catalog.id`). The generated
`plugins/compose-catalogs/.app.json` contains that app ID, not an OAuth client
ID. The MCP endpoint is `https://preview.coo.ee/mcp`. The current replacement
app is [available in the personal directory](https://chatgpt.com/plugins/plugin_asdk_app_6acb43a86b8881918f618daf506c97ef?directoryTab=personal).
Directory visibility and installation remain subject to the host account's access.

1. Check the personal plugin listing and its app dependency. **Install plugin**
   means it is uninstalled; an existing listing has not been deleted. Compare
   its `plugin_asdk_app_…` URL with the exact manifest reference.
2. If reconnecting retains the rejected client ID, stop repeated reconnects.
   The server operator can restore a known registration from trusted metadata
   or backup, binding it to the exact approved callback. Never auto-register
   an unknown client from an incoming authorization URL.
3. Alternatively, create a fresh custom MCP app/connection in the host's plugin
   UI (**Add → Add custom MCP server** where available), with the endpoint
   above and OAuth. If the original name is still reserved, use a distinct
   name such as **Compose Preview Reconnected**. Confirm approval and a gated
   tool call succeed before retiring the old listing. Deleting only a plugin
   wrapper does not establish
   that its underlying app or OAuth registration changed.
4. If the replacement has a new app ID, change
   `src/plugins.json` (`apps.compose-preview-catalog.id`), run
   `python3 scripts/generate.py`, and commit the generated manifests together.
   Use the replacement app's metadata or downloaded plugin ZIP to obtain its
   ID. Preserve the full `plugin_asdk_app_…` technical ID from the browser
   URL as described in [OpenAI's packaging guide](https://developers.openai.com/plugins/build/plugins#create-and-test-a-plugin-locally-with-an-mcp-server);
   do not strip its prefix or substitute an OAuth client ID. Retaining the
   original app ID needs no manifest change.
5. Install the updated plugin and verify hosted catalog discovery and one
   render. Keep the local `compose-preview` stdio server configuration separate.

Durable server registration protects clients registered after the persistence
fix across restarts; it cannot reconstruct registrations lost beforehand.
An unused dynamic registration expires after its configured idle lifetime.
Grants and approval sessions still require renewal. Record the host version
and actual result; a host message saying authentication was requested/accepted
is not proof that OAuth completed or a gated MCP call succeeded.

## Codex local design-to-code acceptance

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
