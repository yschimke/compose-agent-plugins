# Repository consolidation

This is a proposal, not a rule. It belongs next to compose-ai-tools'
[`REPOSITORY_LAYERS.md`](https://github.com/yschimke/compose-ai-tools/blob/main/docs/design/REPOSITORY_LAYERS.md).
It starts here because its first step is in this repository.

## What is shared today

About 26 repositories make up the Compose preview toolchain, counting the `-out` repositories that
CI writes renders into. A byte-for-byte comparison of the ~14,900 tracked files in 16 of them,
taken on 2026-10-04, found little real sharing and a lot of copying.

**Copied code:**

- **`scripts/design-artifacts` exists twice.** compose-ai-tools has 1,386 files and
  compose-preview-server has 1,344. 761 of them are identical; about 600 have drifted apart.
- **About 60 design docs are in both compose-ui-builder and compose-preview-server**, left over
  from the extraction.
- **The Remote Compose player's web build and fonts are copied into five repositories.**
- **Repository plumbing is copied four to seven times**: the attribution scan, git hooks,
  release-PR guards, `agent-gradle.sh`, and the `build-logic` convention plugins.

**Version skew:**

| Repository | Contracts | Daemon |
| --- | --- | --- |
| compose-preview-server | 3.17.0 | 3.14.0 |
| compose-ui-builder | 3.17.0 | 3.13.2 |
| compose-ai-tools | 3.15.0 | 3.13.2 |
| rc-players | 3.13.0 | 3.13.2 |
| compose-preview-xr | 2.20.0 | 3.8.0 |

compose-ai-contrib pins compose-ai-tools at `0.16.15`.

**Release friction:**

- A contracts change takes five releases, one after another, to reach the server.
- A break in one of the builder modules the server compiles against needs matching branches in
  two repositories.
- People add two plugin marketplaces: yschimke/skills and this one.

The genuinely shared surface is small: the wire shapes, the MCP tools, and the skill text.

## The projects that should exist

| Project | Made from | Why |
| --- | --- | --- |
| `compose-preview` (offline engine) | contracts, daemon, rc-players, compose-ai-tools, xr, contrib | One version line and one release. The layer rule stays, enforced by classpath checks such as `checkHttpServerFloor` instead of by repository boundaries. |
| `compose-preview-studio` | compose-preview-server, compose-ui-builder, compose-preview-client | Removes the seam-break process and the duplicated docs. It deploys preview.coo.ee and still builds the desktop and IntelliJ apps. |
| `compose-design-bridges` | design-parity, the one copy of `design-artifacts`, design-map | One home for exporting renders to design tools: Figma (which Codex's design plugins also use), Claude Design through `/design-sync`, and Stitch. |
| `yschimke/skills` | unchanged, widened | Generic skills that work in any agent host: what to do and which tools to call. It grows beyond the preview toolchain into a wider set of Compose and Android UI skills. |
| `compose-agent-plugins` (this repository) | renamed from `compose-ag-plugin` | The harness-specific integrations for previews and the UI builder: per-harness manifests, MCP wiring, hooks, agents, setup and harness-notes skills, and the one marketplace for Claude Code and Codex. |
| `compose-catalogs` | the m3, wear-m3, remote-m3, glimmer and a2ui catalogs | Catalogs we write ourselves, one per `catalogs/<id>/`, with one output repository. |
| `compose-preview-imports` | unchanged | It builds third-party code, so it stays isolated. |
| `compose-preview-vscode` | unchanged | TypeScript, released to its own marketplace. |
| `repo-infra` | `renovate-config`, extended | Reusable workflows for the shared plumbing, and the Gradle conventions as one published plugin. |

## Order

1. **One marketplace.** Done: yschimke/skills is no longer a plugin marketplace, and this
   repository vendors its skills into its own plugins at a pinned commit
   (`scripts/update-skills.py`), one install per host ([adoption](adoption.md)). The earlier
   step, `git-subdir` entries for yschimke/skills' bundles
   ([harness matrix Q22](harness-matrix.md)), is retired.
2. **Draw the line between the two agent repositories.** yschimke/skills stays separate as the
   generic skills, with no host names, install paths, hooks or MCP client config. Harness-specific
   reference material has moved here, and this repository is now named `compose-agent-plugins`. See
   [The two agent repositories](#the-two-agent-repositories).
3. **Move `design-artifacts`, design-map and design-parity into `compose-design-bridges`.** The
   engine and studio then consume a release of it.
4. **Create `repo-infra`.**
5. **Merge the catalogs.**
6. **Fold the builder back into studio**, with a subtree merge so history is kept.
7. **Build the engine monorepo.** It is the largest step and the most debatable, because it gives
   up per-layer repositories for one version line. Steps 1–6 bring most of the benefit without it.

## The two agent repositories

A file belongs in yschimke/skills when it would read the same in any agent host. It belongs here
when it names a host, or configures, installs or works around one.

| Content | Home |
| --- | --- |
| Workflows: render, review, author a design, export to a design tool | yschimke/skills |
| MCP tool and CLI reference: tool names, arguments, results, errors | yschimke/skills |
| Product rules (R1–R4) as they apply to the work | yschimke/skills, stated once and cited here |
| Per-harness manifests, marketplace, MCP client config, hooks, packaged agents | this repository |
| Installing into a host, host detection, host quirks and fallbacks | this repository (`*-setup`, `harness-notes`) |
| Cloud sandboxes of a particular host, and CI agent sessions such as `claude.yml` | this repository |

These moved here on 2026-10-05 into [`host-setup.md`](host-setup.md), each leaving a pointer
behind in yschimke/skills: the per-host parts of `agent-cloud.md`, `mcp.md` and `setup.md`, and the
`claude.yml` specifics of `ci-agent-sessions.md`. `claude-cloud.md`, a stub, was deleted.

yschimke/skills keeps the canonical `skills/` directory, which `npx skills add` and its
`install.sh` read; it no longer ships plugin bundles or a marketplace. This repository copies the
skills its plugins carry into `src/vendor/skills/` at the commit recorded in
`src/vendor/skills/provenance.json`, never edits them, and the `Sync skills` workflow moves the
pin. The design-export and design-parity skills were removed from yschimke/skills.
