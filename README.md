# Compose Agent Plugins

Compose `@Preview` rendering, accessibility checks and hosted component
catalogs for Antigravity, Claude Code, Codex and OpenCode. This repository
holds only the MCP and harness wiring; the Compose skills stay canonical in
[`yschimke/skills`](https://github.com/yschimke/skills).

**Start here:** <https://yschimke.github.io/compose-ai-tools/> for the CLI and your project's previews
(the `compose-preview` plugin); <https://ui.coo.ee/start> for the UI Builder agent flow
(the `compose-catalogs` plugin).

- [Host setup](docs/host-setup.md): per-host install details, the local and
  hosted MCP servers, cloud sandboxes and CI sessions.
- [Troubleshooting](docs/troubleshooting.md) and
  [what works where](docs/harness-matrix.md#status-for-launch).

## Quick start

- `compose-preview` renders your own project's previews locally. It needs Java
  17, a Gradle project and the `compose-preview` CLI: install the CLI with the
  [setup guide](https://github.com/yschimke/skills/blob/main/skills/compose-preview/references/setup.md),
  then the plugin's `compose-preview-setup` skill prepares each project once.
- `compose-catalogs` connects to the hosted Material 3 and Wear catalogs and
  the UI Builder at `https://preview.coo.ee/mcp`. It needs no local toolchain.

Install for your harness below, open your Compose project and try: **"render
the `ListScreenPreview`"** (use one of your own preview function names).

## Install

Details and caveats for each harness are in
[host setup](docs/host-setup.md#install-per-host).

### Antigravity

```sh
curl -fsSL https://raw.githubusercontent.com/yschimke/compose-agent-plugins/main/scripts/antigravity-install.py | python3 - --catalogs
```

### Claude Code

```text
/plugin marketplace add yschimke/compose-agent-plugins
/plugin install compose-skills@compose-agent-plugins
/plugin install compose-preview@compose-agent-plugins
/plugin install compose-catalogs@compose-agent-plugins
```

### Codex

```sh
codex plugin marketplace add yschimke/compose-agent-plugins
# Then enable compose-skills, compose-preview and compose-catalogs from /plugins.
```

### OpenCode

```sh
npx skills add yschimke/skills --global --yes --skill compose-preview --skill compose-ui-builder
curl -fsSL https://raw.githubusercontent.com/yschimke/compose-agent-plugins/main/scripts/opencode-install.py | python3 -
compose-preview mcp install --opencode
```

### Moving from `compose-ag-plugin`

This repository and its marketplace were called `compose-ag-plugin`. GitHub
redirects the old URLs, but the marketplace name changed, so add it again:
in Claude Code `/plugin marketplace remove compose-ag-plugin`, in Codex
`codex plugin marketplace remove compose-ag-plugin`, then add
`yschimke/compose-agent-plugins` and reinstall the plugins under
`@compose-agent-plugins`. In Antigravity, reinstall from the new URLs.

## Updating

See [host setup → Updating](docs/host-setup.md#updating).

## Plugins

- **`compose-preview`**: the local `compose-preview mcp serve` server, a
  post-edit render reminder and an opt-in Stop gate ([hooks](docs/hooks.md)),
  the `design-reviewer` agent, the `compose-preview-setup` onboarding skill,
  the Antigravity-only viewer-card skill and the portable viewer bundle in
  `assets/` ([viewer handoff](src/assets/compose-preview-viewer-fallback.md)).
  The viewer is an unmodified compose-preview-mcp release asset; its
  provenance file pins the release tags, source commit, SHA-256 and MCP Apps
  UI protocol revision, and the `Sync viewer` workflow runs
  `scripts/update-viewer.py <tag>` and opens the pull request on each release.
- **`compose-catalogs`**: the hosted `compose-preview-catalog` server, the
  `compose-catalogs-setup` onboarding skill and, in Codex and ChatGPT, the
  registered Compose Preview app. Access uses an optional token or the
  service's interactive grant.
- Both carry the generated `harness-notes` skill, which summarizes the
  [agent rules](docs/agent-rules.md) (R1–R4) for the active harness.
- The OpenCode bundle under `opencode/` carries the same agent, rules skill
  and edit reminder; see [OpenCode](docs/opencode.md).

`design-reviewer` runs semantic, accessibility, font-scale, device and
catalog-guidelines checks in its own context and returns a short verdict, so
rendered images stay out of the main conversation. Guidelines reviews work in
all four harnesses through the canonical checklist in `compose-skills`; see
[guidelines review setup and fallbacks](docs/design-guidelines-review.md) and
the [cross-harness evals](evals/README.md).

Everything under `plugins/`, every manifest, `gemini-extension.json`,
`server.json` and `opencode/` is generated: edit
[`src/plugins.json`](src/plugins.json) or the files under `src/`, then run
`python3 scripts/generate.py`. [Distribution](docs/distribution.md) lists what
each listing receives.

## Development

Run the repository gate before sending a change; CI also runs the drift
regression tests and markdownlint:

```sh
scripts/check-plugins.sh
tests/check_plugins_test.sh
npx markdownlint-cli2 "**/*.md"
```

Other scripts:

- `python3 scripts/antigravity-install.py [--catalogs] [--dry-run]`: install or
  update the Antigravity plugins from GitHub, clearing stale entries first.
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
The externally referenced skill bundles keep their own release process in `yschimke/skills`.

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
