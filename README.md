# Compose Agent Plugins

Let your agent see your Compose UI: start at <https://yschimke.github.io/compose-ai-tools/>.
Designing a new screen with an agent? Start at <https://ui.coo.ee/start>.

## Quick start

Install one plugin, `compose-preview`, for your host.

Claude Code:

```text
/plugin marketplace add yschimke/compose-agent-plugins
/plugin install compose-preview@compose-agent-plugins
```

Codex:

```sh
codex plugin marketplace add yschimke/compose-agent-plugins
```

then enable `compose-preview` from `/plugins`.

Antigravity:

```sh
curl -fsSL https://raw.githubusercontent.com/yschimke/compose-agent-plugins/main/scripts/antigravity-install.py | python3 -
```

OpenCode:

```sh
npx skills add yschimke/skills --global --yes --skill compose-preview --skill compose-ui-builder
curl -fsSL https://raw.githubusercontent.com/yschimke/compose-agent-plugins/main/scripts/opencode-install.py | python3 -
compose-preview mcp install --opencode
```

Any other agent (Gemini CLI, Cursor, Copilot, …), or no plugin system:

```sh
curl -fsSL https://raw.githubusercontent.com/yschimke/skills/main/scripts/install.sh | bash
```

Then ask your agent to render one of your previews. Details and caveats for
each host are in [other hosts](docs/host-setup.md#install-per-host); when
something goes wrong, see [troubleshooting](docs/troubleshooting.md).

**No shell or Java?** In Claude chat, Cowork or ChatGPT, or to use only the UI
Builder and the hosted catalogs without a JDK, install `compose-catalogs`
instead (in Antigravity, `antigravity-install.py --catalogs`), or add the hosted
MCP server `https://preview.coo.ee/mcp` directly. Don't install both:
`compose-preview` already carries that server.

## Plugins

- **`compose-preview`**: the one plugin for coding agents. Renders your
  project's previews through the local `compose-preview mcp serve` server and
  reaches the hosted catalogs and UI Builder through `compose-preview-catalog`;
  ships the `compose-preview` and `compose-ui-builder` skills.
- **`compose-catalogs`**: the hosted server, the `compose-ui-builder` skill and,
  in Codex and ChatGPT, the registered Compose Preview app, for hosts with no
  shell or Java.
- **`compose-review`** (optional): the `compose-preview-review` and
  `compose-preview-ci` skills, to review Compose UI pull requests and set up CI
  that posts before/after previews. Your agent offers it when it is relevant.

What each plugin contains, its hooks and the data it sends are in its README
under [`plugins/`](plugins/), the [hooks](docs/hooks.md) doc and
[distribution](docs/distribution.md).

## Moving from compose-ag-plugin

This repository and its marketplace were called `compose-ag-plugin`. GitHub
redirects the old URLs, but the marketplace name changed, so add it again:
in Claude Code `/plugin marketplace remove compose-ag-plugin`, in Codex
`codex plugin marketplace remove compose-ag-plugin`, then add
`yschimke/compose-agent-plugins` and reinstall the plugins under
`@compose-agent-plugins`. In Antigravity, reinstall from the new URLs.

**Moving from the split install.** `compose-preview` now carries the skills and
the hosted server itself. Uninstall `compose-skills`, `compose-review-skills`
and `compose-design-skills`, remove the `yschimke-skills` marketplace, and on a
coding agent uninstall `compose-catalogs`; install `compose-review` if you used
the review skills. In Antigravity, rerun the installer, which does this for
you. The design-export and design-parity skills were removed; they remain in
the [`yschimke/skills` history](https://github.com/yschimke/skills/commits/main).

## Updating

See [host setup → Updating](docs/host-setup.md#updating).

## Development

Read [adoption](docs/adoption.md) before adding a default skill, a plugin or a
front-door install step: it is the rule for what loads by default and what is
reached through next-step hints.

Everything under `plugins/`, every manifest, `gemini-extension.json`,
`server.json` and `opencode/` is generated: edit
[`src/plugins.json`](src/plugins.json) or the files under `src/`, then run
`python3 scripts/generate.py`. The `compose-preview`, `compose-ui-builder`,
`compose-preview-review` and `compose-preview-ci` skills are vendored from
[`yschimke/skills`](https://github.com/yschimke/skills) into `src/vendor/skills/`
by `python3 scripts/update-skills.py <ref>` (or `--from-local <clone> <ref>`),
which records the commit in `src/vendor/skills/provenance.json`; never edit
them here. The `Sync skills` workflow does that daily and opens a pull request.
The viewer in `src/assets/` is an unmodified compose-preview-mcp release asset,
pinned the same way by `scripts/update-viewer.py <tag>` and the `Sync viewer`
workflow.

Run the repository gate before sending a change; CI also runs the drift
regression tests and markdownlint:

```sh
scripts/check-plugins.sh
tests/check_plugins_test.sh
npx markdownlint-cli2 "**/*.md"
```

Other scripts:

- `python3 scripts/antigravity-install.py [--catalogs] [--dry-run]`: install or
  update `compose-preview` (or `compose-catalogs` instead) in Antigravity from
  GitHub, clearing stale and retired entries first.
- `python3 scripts/antigravity-check.py`: plugin copies, MCP-only `gemini-cli` imports, card helper, CLI
  `preview=`/`project=` support, duplicate global MCP entries, stale servers.
- `python3 scripts/opencode-install.py [--dry-run] [--config-dir DIR]`: install
  or update the OpenCode bundle and add the MCP servers to `opencode.json`.
- `python3 scripts/opencode-check.py [--run --project …]`: skills, bundle, MCP config,
  `opencode mcp list`, and optionally one timed model turn.
- `python3 scripts/edit-render-bench.py --help`: time the edit → notify →
  render loop against the local server without a model.

## Releases

Release Please opens a release PR from Conventional Commits on `main`. A human merges it to
create a `vX.Y.Z` tag and GitHub release; releases always bump the minor version. The baseline
is the plugins' existing `0.3.0` version. The release PR updates `version.txt`, the release
manifest, and the local plugin and Gemini versions in `src/plugins.json`, then regenerates the
harness manifests with `scripts/generate.py`. Do not bump generated manifests by hand.

The validation workflow is explicitly dispatched on the release branch, because PRs and commits
created with `GITHUB_TOKEN` do not start `pull_request` workflows. The release workflow can also
be dispatched on `main` to retry an interrupted pass. No PR is automatically merged.

Tags version this repository's plugin packaging. The MCP Registry version still belongs to
`compose-preview-server` and is published by `mcp-registry.yml`; release-please does not bump it.
The vendored skills follow `yschimke/skills`; a `Sync skills` pull request moves them.

Repository setup: enable **Allow GitHub Actions to create and approve pull requests**, keeping
default workflow permissions read-only. The workflows request write access only in release jobs.
An optional `RELEASE_PLEASE_TOKEN` can supply a repository-scoped token when GitHub's default
token cannot create a release containing workflow changes; ordinary runs use `GITHUB_TOKEN`.

## Repository merge policy

Repository settings and required checks are managed by
[yschimke/renovate-config](https://github.com/yschimke/renovate-config/tree/main/repo-policy).
Pull requests use Conventional Commit titles and squash merges. Run
`scripts/install-git-hooks.sh` to enable the same attribution checks locally.

Release Please starts its first changelog after commit
`3fba026254eade5fd850916efa08885ed501c4c9`, which established the `0.3.0`
version manifest. The `bootstrap-sha` setting is ignored after the first release
PR merges; subsequent notes use the preceding release. This avoids importing
all pre-baseline history into the first automated release.
