# Changelog

## [0.8.0](https://github.com/yschimke/compose-agent-plugins/compare/v0.7.0...v0.8.0) (2026-10-31)


### Features

* **antigravity:** add Compose Preview sidecar, SessionStart hook, and launch simulator support ([#164](https://github.com/yschimke/compose-agent-plugins/issues/164)) ([fa6e46e](https://github.com/yschimke/compose-agent-plugins/commit/fa6e46eb7a51379561b74f7ff59c8b4289c315e8))
* **mods:** prototype a compose-preview pane mod ([#163](https://github.com/yschimke/compose-agent-plugins/issues/163)) ([d6e8365](https://github.com/yschimke/compose-agent-plugins/commit/d6e83654fb396033255a14bd8ad1679057f81f2b))
* **viewer:** bundle the compose-preview-server v3.131.0 viewer, and add a one-command viewer update ([#151](https://github.com/yschimke/compose-agent-plugins/issues/151)) ([f584c8d](https://github.com/yschimke/compose-agent-plugins/commit/f584c8d479fc9a03ca8bc544d162e6f1980fe91c))
* **viewer:** take the bundled viewer from compose-preview-mcp releases ([#154](https://github.com/yschimke/compose-agent-plugins/issues/154)) ([d329edb](https://github.com/yschimke/compose-agent-plugins/commit/d329edbabb50397e6e46ee00002752aae43f25f4))


### Bug Fixes

* bundle the viewer from compose-preview-mcp v4.0.0 ([#155](https://github.com/yschimke/compose-agent-plugins/issues/155)) ([80c6745](https://github.com/yschimke/compose-agent-plugins/commit/80c674562c7d5a8961e651e046780d8527f24613))
* bundle the viewer from compose-preview-mcp v4.12.0 ([#162](https://github.com/yschimke/compose-agent-plugins/issues/162)) ([c2dd317](https://github.com/yschimke/compose-agent-plugins/commit/c2dd317ed87880f99227632fe7f12ede318e2c3c))
* **mods:** match the compose-preview CLI and MCP server as ComposeStarter answers them ([#166](https://github.com/yschimke/compose-agent-plugins/issues/166)) ([ff17bea](https://github.com/yschimke/compose-agent-plugins/commit/ff17bea451fd1216b324742f54a1b8843a12f41f))
* **sidecar:** resolve open workspace from Antigravity hooks, env, and MCP registry ([#167](https://github.com/yschimke/compose-agent-plugins/issues/167)) ([75f3abf](https://github.com/yschimke/compose-agent-plugins/commit/75f3abff58af98b650294863f85e60bddf2ab83f))

## [0.7.0](https://github.com/yschimke/compose-agent-plugins/compare/v0.6.0...v0.7.0) (2026-10-12)


### Features

* **hooks:** put an installed compose-preview CLI on Claude Code's PATH and clear legacy installer env entries ([#145](https://github.com/yschimke/compose-agent-plugins/issues/145)) ([dfcdeee](https://github.com/yschimke/compose-agent-plugins/commit/dfcdeee810574b57f805387e88f012b4ad4fd3a1))


### Bug Fixes

* **design-reviewer:** load in Antigravity, keep local reviews local, and support the CLI path without MCP ([#148](https://github.com/yschimke/compose-agent-plugins/issues/148)) ([2b85706](https://github.com/yschimke/compose-agent-plugins/commit/2b857062f277c754bcf74b92dbb5d30bd775bfd5))

## [0.6.0](https://github.com/yschimke/compose-agent-plugins/compare/v0.5.0...v0.6.0) (2026-10-11)


### Features

* **codex:** streamline local design-to-code workflows ([#136](https://github.com/yschimke/compose-agent-plugins/issues/136)) ([f64506e](https://github.com/yschimke/compose-agent-plugins/commit/f64506e2275938cf6cc0e3df1a3de2d808600769))
* fix Claude reviewer tool names, add Antigravity rules and an OpenCode bundle ([#139](https://github.com/yschimke/compose-agent-plugins/issues/139)) ([fe12460](https://github.com/yschimke/compose-agent-plugins/commit/fe12460d85d6fd35d0dbd1f9af3302b96ba6fe49))


### Bug Fixes

* **codex:** replace expired Compose Preview app registration ([#142](https://github.com/yschimke/compose-agent-plugins/issues/142)) ([05c4453](https://github.com/yschimke/compose-agent-plugins/commit/05c445345fff28a5ee23a42faf98b3d0a8ad9c4f))
* **design-reviewer:** return findings for a recorded-home design when publishing is not authorized ([#138](https://github.com/yschimke/compose-agent-plugins/issues/138)) ([516d14c](https://github.com/yschimke/compose-agent-plugins/commit/516d14c85c32be0485087c5b6dfea8038cdcda37))
* regenerate the OpenCode design-reviewer agent ([#140](https://github.com/yschimke/compose-agent-plugins/issues/140)) ([090d166](https://github.com/yschimke/compose-agent-plugins/commit/090d166fcf63be3748c483deb1adb86818a8ba11))

## [0.5.0](https://github.com/yschimke/compose-agent-plugins/compare/v0.4.0...v0.5.0) (2026-10-10)


### Features

* present audit results consistently across agents ([#132](https://github.com/yschimke/compose-agent-plugins/issues/132)) ([a94e0fb](https://github.com/yschimke/compose-agent-plugins/commit/a94e0fb3b7d882141259ce5ab103fde5cecac67e))

## [0.4.0](https://github.com/yschimke/compose-agent-plugins/compare/v0.3.0...v0.4.0) (2026-10-10)


### Features

* route catalog guideline reviews across supported agents ([59e73de](https://github.com/yschimke/compose-agent-plugins/commit/59e73dead308a12334a852b3304d9d04294ce00e))
* route catalog guideline reviews across supported agents ([b67019c](https://github.com/yschimke/compose-agent-plugins/commit/b67019c771bcbc2ebc69d0b8ba1beb707d296edc))


### Bug Fixes

* bootstrap release notes and adopt shared merge policy ([7b6e854](https://github.com/yschimke/compose-agent-plugins/commit/7b6e854056573d5cac2011ef3ef10dd23142f596))
* bootstrap release notes and adopt shared merge policy ([79b565b](https://github.com/yschimke/compose-agent-plugins/commit/79b565b39b4120b8743561e3bd5fd5b84de23005))

## Baseline

Release notes are maintained by release-please after this baseline.
