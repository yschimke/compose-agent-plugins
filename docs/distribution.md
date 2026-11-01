# Distribution

Where the plugins and the hosted server are listed, what this repository
generates for each listing, and what still needs an account or a person. Every
file named here is generated from [`src/plugins.json`](../src/plugins.json) by
`python3 scripts/generate.py`; edit the source, never the output.

The marketplace lists three plugins built here: `compose-preview` (the one
plugin for coding agents: both MCP servers and the `compose-preview` and
`compose-ui-builder` skills), `compose-catalogs` (the hosted server and
`compose-ui-builder`, for hosts with no shell or Java, and the source of the
registry entry and the ChatGPT app) and the optional, skills-only
`compose-review`. The generic skills are vendored from yschimke/skills at the
commit in `src/vendor/skills/provenance.json` (`scripts/update-skills.py`); the
marketplace no longer lists any plugin from another repository.

| Listing | Issue | Generated here | CI check | Still needs |
| --- | --- | --- | --- | --- |
| Claude plugin directory | [#53](https://github.com/yschimke/compose-agent-plugins/issues/53) | `plugins/*/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `plugins/*/README.md`, `plugins/*/LICENSE` | `claude plugin validate --strict` on every plugin and the marketplace | Portal **Validate**, submission, tracked branch or tag ([#80](https://github.com/yschimke/compose-agent-plugins/issues/80)) |
| Official MCP Registry | [#55](https://github.com/yschimke/compose-agent-plugins/issues/55) | `server.json` | Upstream `server.schema.json` | Nothing: published, and republished for each server release (below) |
| Cursor Marketplace | [#59](https://github.com/yschimke/compose-agent-plugins/issues/59) | `plugins/*/.cursor-plugin/plugin.json`, `.cursor-plugin/marketplace.json` | Cursor's `plugin.schema.json` and `marketplace.schema.json` | Smoke test ([#79](https://github.com/yschimke/compose-agent-plugins/issues/79)), submission ([#81](https://github.com/yschimke/compose-agent-plugins/issues/81)) |
| Gemini CLI extensions gallery | [#58](https://github.com/yschimke/compose-agent-plugins/issues/58) | `gemini-extension.json` | `gemini extensions validate` | Smoke test with the local CLI ([#78](https://github.com/yschimke/compose-agent-plugins/issues/78)); the gallery crawls the `gemini-cli-extension` topic, which is set |
| Claude Connectors Directory | [#54](https://github.com/yschimke/compose-agent-plugins/issues/54) | — | — | Tool titles and annotations and OAuth in compose-preview-server, then submission ([#83](https://github.com/yschimke/compose-agent-plugins/issues/83)) |
| skills.sh | [#57](https://github.com/yschimke/compose-agent-plugins/issues/57) | — | — | The canonical skills live in yschimke/skills, which `npx skills add` reads; indexing check ([#84](https://github.com/yschimke/compose-agent-plugins/issues/84)) |

## The Compose Preview token

The hosted server reads an optional `X-Compose-Preview-Token` header. Each
harness gets it differently, and all of them come from the one `userConfig`
entry and `envHeaders` mapping in `src/plugins.json`:

| Harness | Header value | Where the user sets it |
| --- | --- | --- |
| Claude Code | `${user_config.compose_preview_token}` | Prompted when the plugin is enabled; stored in the credential store |
| Codex | `env_http_headers` → `COMPOSE_PREVIEW_TOKEN` | Environment |
| Antigravity | `${COMPOSE_PREVIEW_TOKEN:-}` | Environment |
| Cursor | `${COMPOSE_PREVIEW_TOKEN}`, declared in `variables` | Plugin variables (unverified) |
| Gemini CLI | `${COMPOSE_PREVIEW_TOKEN}`, declared in `settings` | Environment (checked); `gemini extensions config` (unverified) |

Claude Code no longer reads `COMPOSE_PREVIEW_TOKEN` from the environment. The
directory holds a plugin that forwards a credential from the user's environment
for review, so the Claude manifest takes it from a sensitive `userConfig`
option instead. A blank option sends an empty header, and the server still
connects (checked with Claude Code 2.1.285).

## Claude plugin directory

The [pre-submission checklist](https://claude.com/docs/plugins/pre-submission-checklist)
was worked through on 2026-09-30. Fixed here: a README of at least 40 words and
a LICENSE in each plugin folder, `displayName`, a marketplace description, and
the token (above). `scripts/validate_manifests.py` enforces the README length
and the no-environment-credential rule.

Expected reviewer holds that are not bugs. The plugins live in subfolders of a
marketplace repository, so the validator follows only plain shell scripts:

- `compose-preview` starts `compose-preview mcp serve` from `PATH`, not a file
  in the plugin (**MCP server command wasn't read**). The CLI needs Java and
  Gradle, so it can't be bundled.
- The hook scripts source `scripts/lib/harness.sh` and use shell variables
  (**Scripts the validator couldn't follow**).
- `compose-preview` only works fully where a local shell and JDK exist, so it is
  a Claude Code plugin; chat and Cowork use `compose-catalogs`, which carries the
  same hosted server without the local one.

Each plugin README lists what the plugin runs and what it sends, for the
security scan's undisclosed-destination check.

## Official MCP Registry

`server.json` lists the hosted server as `io.github.yschimke/compose-preview`,
a `streamable-http` remote at `https://preview.coo.ee/mcp` with the optional
secret header. The local server has no registry package type (it is a JVM CLI
launched from `PATH`), so it is not listed.

[`.github/workflows/mcp-registry.yml`](../.github/workflows/mcp-registry.yml)
publishes it with `mcp-publisher` and GitHub OIDC, so no secret is needed. It
sets `version` to the compose-preview-server release, and skips a version the
registry already has. It runs:

- daily, for the newest `vX.Y.Z` tag of compose-preview-server;
- on a `repository_dispatch` of type `compose-preview-server-release` with
  `client_payload.version`, which that repository's release workflow can send;
- by hand, with an optional version.

The first run, started by hand on 2026-09-30, published version 3.88.0
([run](https://github.com/yschimke/compose-agent-plugins/actions/runs/36775847035)).
Whether the listing shows up at github.com/mcp and in the VS Code `@mcp` gallery
still needs checking.

## Cursor

Cursor reads `.cursor-plugin/marketplace.json` at the repository root and
`.cursor-plugin/plugin.json` in each plugin folder. The MCP servers are inline
in the manifest. `compose-preview` sets `hooks` to an empty inline config
because Cursor would otherwise discover `hooks/hooks.json`, which holds Claude
Code hooks whose event names and payloads Cursor does not share. Whether the
inline config replaces that discovery, and whether Cursor expands the token
variable in headers, is unverified until a smoke test.

## Gemini CLI

Gemini CLI reads `gemini-extension.json` only from the root of a repository or
release archive, so this repository ships one extension, `compose-preview`,
that wraps the servers of the `compose-preview` plugin: the local
`compose-preview-mcp` and the hosted `compose-preview-catalog`, each listed
once. It carries no skills, hooks or agents; the repository root has none, and
Gemini CLI users take the skills from yschimke/skills' `install.sh`.
Install with `gemini extensions install https://github.com/yschimke/compose-agent-plugins`.

Checked on 2026-09-30 with Gemini CLI 0.62.0 on Linux, using the script in
[#78](https://github.com/yschimke/compose-agent-plugins/issues/78):

- `gemini extensions validate` passes, and so does install from a local clone.
  Install asks the user to trust the folder even with `--consent`, and warns
  about the missing token setting although it is optional.
- With `COMPOSE_PREVIEW_TOKEN` set in the environment, the header reached a
  local echo server with that value. With it unset, the header was empty and
  the server still connected. Declaring the variable in `settings` is what lets
  it through.
- The hosted catalog connected with no token.

Not yet checked, and asked for in #78: `compose-preview-mcp` with the CLI
installed, a real render, a token set through `gemini extensions config`
(stored in the system keychain), whether Antigravity loads the extension, and
the gallery listing.
