# Compose Agent Plugins

Compose `@Preview` rendering, accessibility checks and remote component
catalogs for Antigravity, Claude Code, Codex and OpenCode. This repository
holds only the MCP and harness wiring; the Compose skills stay canonical in
[`yschimke/skills`](https://github.com/yschimke/skills).

Something not working? See [Troubleshooting](docs/troubleshooting.md).
Per-host details (MCP registration, skill locations, cloud sandboxes, CI sessions):
[Host setup notes](docs/host-setup.md).
What works where: [status for launch](docs/harness-matrix.md#status-for-launch).

## Quick start

Local rendering (`compose-preview`) needs Java 17, a Gradle project with
`@Preview`s, and the `compose-preview` CLI on `PATH`:

```sh
curl -fsSL https://raw.githubusercontent.com/yschimke/skills/main/scripts/install.sh | bash -s -- --cli-only
compose-preview --version   # open a new terminal first if this is not found
```

Then prepare each Compose project once, from its root folder. Without this the
first render fails with "project not prepared … run `compose-preview mcp
install` once":

```sh
cd path/to/your/project
compose-preview mcp install
```

`compose-catalogs` (hosted Material 3 and Wear catalogs, UI Builder) needs no
local toolchain. In Codex and ChatGPT it also declares the registered Compose
Preview app: the app hosts the preview/review surface returned by the server,
while the full UI Builder stays in its dedicated editor. Then pick your harness.
In every harness, open your Compose project and try: **"render the
`ListScreenPreview`"** (use one of your own preview function names).

### Antigravity

```sh
agy plugin install https://github.com/yschimke/skills/tree/main/plugins/compose-skills
agy plugin install https://github.com/yschimke/compose-agent-plugins/tree/main/plugins/compose-preview
agy plugin enable compose-preview
# Optional: hosted Material 3 / Wear catalogs and UI Builder.
agy plugin install https://github.com/yschimke/compose-agent-plugins/tree/main/plugins/compose-catalogs
```

Or run the same steps in one go; it also updates an existing install
(uninstalling first, including a stale MCP-only `compose-preview`) and stops
old `compose-preview mcp serve` processes. Drop `--catalogs` to skip the
catalogs; add `--dry-run` to print the commands only:

```sh
curl -fsSL https://raw.githubusercontent.com/yschimke/compose-agent-plugins/main/scripts/antigravity-install.py | python3 - --catalogs
```

Use the `/tree/main/plugins/<name>` URL: `agy` clones the repository and
installs that folder. The bare repository URL installs only the two MCP servers
from the root `gemini-extension.json` (no skills, agents or hooks) under the
same `compose-preview` name. A local checkout still works
(`agy plugin install ./compose-agent-plugins/plugins/compose-preview`), and
`python3 compose-agent-plugins/scripts/antigravity-check.py` from a clone verifies
the install.

Install skills from `yschimke/skills` as plugins, not with
`npx skills add … --agent antigravity`: Antigravity 1.2.12 does not load
`~/.agents/skills` (issue #6 Q14). `compose-skills` is the default pair
(`compose-preview`, `compose-ui-builder`); add `compose-review-skills` or
`compose-design-skills` from the same `/tree/main/plugins/<name>` path when
you need them. The bare `yschimke/skills` URL installs all eight as
`yschimke-skills`; don't keep it next to a bundle. The wiring plugins do not
install the canonical skills.

### Moving from `compose-ag-plugin`

This repository and its marketplace were called `compose-ag-plugin`. GitHub redirects the old URLs,
but the marketplace name changed, so an existing Claude Code or Codex install keeps the old name
until you add the marketplace again:

```text
/plugin marketplace remove compose-ag-plugin
/plugin marketplace add yschimke/compose-agent-plugins
```

In Codex, `codex plugin marketplace remove compose-ag-plugin`, then add
`yschimke/compose-agent-plugins`. Then reinstall the plugins below under `@compose-agent-plugins`.
Antigravity installs by URL, so reinstall from the new URLs to pick up later changes.

### Claude Code

```text
/plugin marketplace add yschimke/compose-agent-plugins
/plugin install compose-skills@compose-agent-plugins
/plugin install compose-preview@compose-agent-plugins
/plugin install compose-catalogs@compose-agent-plugins
```

This one marketplace also lists the canonical skill bundles, which it installs straight from
`yschimke/skills` (`compose-skills`, and optionally `compose-review-skills` and
`compose-design-skills`). If you installed them earlier from the `yschimke-skills` marketplace,
uninstall that copy, or each skill loads twice.

Verify: restart, then `/mcp` lists `plugin:compose-preview:compose-preview-mcp`
as connected. Enabling `compose-catalogs` asks for an optional Compose Preview
token; Claude Code does not read `COMPOSE_PREVIEW_TOKEN` from the environment.

### Codex

```sh
codex plugin marketplace add yschimke/compose-agent-plugins
# Then enable compose-skills, compose-preview and compose-catalogs from /plugins.
```

As in Claude Code, `compose-skills` comes from `yschimke/skills` through this marketplace; drop a
separate `yschimke/skills` marketplace if you added one before.

Verify: `codex mcp list` shows `compose-preview-mcp` and
`compose-preview-catalog`. Approve the plugin hooks when Codex marks them
untrusted.

### OpenCode

OpenCode has no plugin marketplace; install the skills, the OpenCode bundle and the server:

```sh
npx skills add yschimke/skills --global --yes --skill compose-preview --skill compose-ui-builder
curl -fsSL https://raw.githubusercontent.com/yschimke/compose-agent-plugins/main/scripts/opencode-install.py | python3 -
compose-preview mcp install --opencode
# Verify
python3 scripts/opencode-check.py   # from a clone of this repository
```

`opencode-install.py` copies the generated [`opencode/`](opencode) bundle into
`~/.config/opencode`: the `design-reviewer` subagent, the `harness-notes` rules
skill and the [edit reminder](#compose-edit-reminder) plugin. It also adds both
MCP servers and read access to rendered PNGs to `opencode.json`, keeping
existing entries. Rerun it to update.

The first `mcp install` resolves the project through Gradle and can take several
minutes, so don't run it under a two-minute command timeout. If your OpenCode
config is `opencode.jsonc` or has comments, `mcp install` prints a snippet
instead of editing it: merge that snippet by hand (the check prints it too).
OpenCode 1.18 and later (the npm `latest`) and v2 both read it.

See [OpenCode](docs/opencode.md) for the catalog server and authentication.

## Updating

```sh
compose-preview update   # CLI (and PATH)
npx skills update        # skills installed with npx
```

- Claude Code and Codex: update the marketplaces and plugins from `/plugin`
  or `/plugins`.
- Antigravity copies plugins at install time, and installing over an existing
  plugin keeps its old record in `agy plugin list`. To pick up `main`, rerun
  the [one-step install](#antigravity), or `agy plugin uninstall <name>` and
  then its `agy plugin install` line.
- If renders look out of date after an update, clear the server cache
  (`rm -rf ~/.cache/composeai/preview-mcp`) and restart the harness. This is
  needed until yschimke/compose-ai-tools#5602 ships.

## Plugins

`compose-catalogs` connects agents to remote discovery and rendering of Compose
Material 3 and Wear components, plus semantic UI-builder authoring and Kotlin
export. It has no local toolchain prerequisite because it connects to the
hosted preview MCP service. Access uses an optional token (`COMPOSE_PREVIEW_TOKEN`,
or the plugin's token setting in Claude Code) or the service's interactive grant
flow.

`compose-preview` supplies the local `compose-preview mcp serve` connection for
iterative Compose rendering and accessibility checks. It requires Java 17,
Gradle, and the `compose-preview` CLI on the workstation. It also ships a
[post-edit render reminder](#compose-edit-reminder) and an opt-in
[Stop gate](#compose-preview-stop-gate). The rendering workflow itself comes
from the canonical `compose-preview` skill in `yschimke/skills`.

Both wiring plugins include the same generated `harness-notes` micro-skill. It
summarizes R1–R4 for the active harness and points back to the full contract; it
does not duplicate the canonical Compose workflows. Edit its single source at
[`src/skills/harness-notes/SKILL.md`](src/skills/harness-notes/SKILL.md), then
run the generator.

`compose-preview` additionally carries the Antigravity-only viewer-card
micro-skill. Keeping that instruction out of `compose-catalogs` avoids
advertising a local artifact that the remote-catalog plugin does not package.

`compose-preview` also ships the `design-reviewer` agent for Claude
Code and Antigravity, and the OpenCode bundle carries the same agent as an
OpenCode subagent with the same tool boundary. It uses the `compose-catalogs` tools too when that plugin
is installed, so it ships once rather than in both plugins. It runs semantic,
accessibility, font-scale, device and catalog-guidelines checks in its own context and returns a
short verdict with viewer or artifact links, so rendered images stay out of the
main conversation.
Antigravity 1.2.12 discovered and ran a plugin fixture agent (issue #6 Q20);
Codex support remains unverified.

Requested guidelines reviews work in **all four harnesses**, including a
catalog-only install, through the canonical checklist in the default
`compose-skills` bundle. Without a discoverable reviewer agent, run it in the
current context. The reviewer preserves source and design nodes; it may record
requested guideline results at the design's home. Start with a keyless prompt
or a published result; a provider key is optional. Missing evidence produces a
partial review, and model warnings never block export or the Stop gate.
See [guidelines review setup and fallbacks](docs/design-guidelines-review.md)
and the [cross-harness evals](evals/design-guidelines.md).

`compose-preview` also ships the portable viewer bundle at
`assets/compose-preview-viewer.html`, the unmodified `compose-preview-viewer.html`
asset from the compose-preview-server v3.77.0 release; the adjacent provenance
file pins that release tag, its source commit, the SHA-256, and the stable MCP
Apps UI protocol revision. Antigravity renders `<agent-embed>` cards as
`iframe srcdoc`, which drops the URL fragment the viewer reads (issue #6 Q9), so
`assets/compose-preview-card.py` appends the result to a copy of the viewer as
an inline `<script type="application/json" id="compose-preview-result">` block
instead. It reads the PNG from the `pngPath` that `render_preview` returns with
`inline=false`, so the agent never prints base64. The `antigravity-viewer-card`
skill runs it; `assets/compose-preview-viewer-fallback.md` has the contract and
the text fallback.

Every plugin follows the [agent rules](docs/agent-rules.md): the agent sees what the user sees, edits through typed tools with schemas, edits a design at its one canonical home, and keeps discussion there.

The generated manifests make the same plugin directories usable by every
harness. The generator also writes each plugin's `README.md` and `LICENSE`, the
Cursor manifests, the root `gemini-extension.json`, the MCP Registry
`server.json`, the Antigravity `rules/AGENTS.md` (from `src/rules/`) and the
OpenCode bundle under `opencode/`; see [Distribution](docs/distribution.md) for the listings they
serve. Edit [`src/plugins.json`](src/plugins.json) and run
`python3 scripts/generate.py`; never edit a manifest directly.

The [agent rule evals](evals/agent-rules.md) and the other cross-harness
prompts that verify the upstream skills together with this wiring live in
[`evals/`](evals/README.md).

## Compose edit reminder

After the agent edits a `*.kt` file that declares a `@Composable` or `@Preview`,
the `compose-preview` plugin's PostToolUse hook adds one line of context: render
an affected preview with `render_preview` and look at it before calling the
change done (agent rule R1). A hook is always seen; a skill is not, and in
the eval run on #64 agents edited Compose UI without rendering even with the
skill offered (#86).

It reminds once per file per session, never blocks, and stays silent when the
edit touched no Compose file or when anything about the hook itself fails. It
runs in Claude Code (`Edit`, `Write`, `MultiEdit`) and Codex (`apply_patch`).
In OpenCode the same reminder is a plugin, `opencode/plugins/compose-preview.js`,
that appends the line to the `edit`, `write` or `apply_patch` result.
Antigravity gets only Stop hooks for now: its post-edit tool names differ and
its context output for that event has not been verified. Instead the
`compose-preview` plugin ships `rules/AGENTS.md`, which Antigravity loads on
every turn: render first with `project=<workspace>`, render after editing
Compose UI, and check `compose-preview design status` before finishing design
work. Claude Code ignores a plugin's `rules/`.

In a Gradle workspace, the SessionStart hook in Claude Code and Codex also adds
one routing line: call `render_preview` by name before searching the project,
and take library components from the hosted catalog rather than writing preview
files. It targets the grep-before-render and catalog-routing failures in the
evals on #64 (T5, H6).

## Compose Preview Stop gate

The `compose-preview` plugin's Stop hook does nothing unless
`COMPOSE_PREVIEW_GATE=1` is set in the environment the harness starts hooks
with. When it is set, the hook looks at previews declared in `*.kt` files that
differ from `HEAD` or are untracked. It runs `compose-preview show --json` and
`compose-preview a11y --json --fail-on errors`. It keeps the agent working
only when one of those previews:

- fails to render; or
- has accessibility errors. Warnings do not count.

It never blocks on image, hash or pixel changes, because a migration is
expected to change pixels (#10).

The gate lets the agent stop in these cases:

- a Stop hook already continued this turn (`stop_hook_active`);
- two turns in a row were already blocked in this session;
- `compose-preview`, `git` or `python3` is missing;
- the CLI fails, times out, or prints output the gate cannot parse.

Each CLI call is bounded by `COMPOSE_PREVIEW_GATE_TIMEOUT` seconds (default
150). A Gradle build that fails before it reports any previews counts as a tool
error, not a render failure.

When `ui-builder/designs/index.json` exists, the gate also asks
`compose-preview design status` about unacknowledged design comments (R4) and
unsaved temporary copies (R3). It reports them to the person but never blocks
because of them.

Each harness gets its own generated hook manifest, and every command passes
its harness explicitly:

- Claude Code (`hooks/hooks.json`, `--harness=claude`) and Codex
  (`hooks/codex-hooks.json`, `--harness=codex`) use the
  `{"decision":"block","reason":…}` response.
- Antigravity (the root `hooks.json`, `--harness=antigravity`) uses
  `{"decision":"continue","reason":…}`. It has no SessionStart event, so it
  gets only the Stop gate, run from the installed copy under
  `~/.gemini/config/plugins/compose-preview`. Its Stop payload has no
  `stop_hook_active` and #6 Q4 observed no host cap, so the two-turn cap,
  keyed by `conversationId`, is the only loop guard. The gate finds the
  checkout from the first `workspacePaths` entry. Antigravity has no
  non-blocking Stop message, so the design reminder is not shown there. A live
  Antigravity block has not been recorded yet (#39).

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
