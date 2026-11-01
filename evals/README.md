# Skill and wiring evals

These prompts test the canonical skills from
[`yschimke/skills`](https://github.com/yschimke/skills), as vendored into this
repository's plugins, together with its MCP wiring. They do not describe skills
written in this repository.

For each run, record the harness and version, canonical-skills commit (the
`commit` in `src/vendor/skills/provenance.json`), plugin commit, result, tool sequence, image count, and any follow-up issue. Do not mark
an eval as passed from static inspection alone.

- [`agent-rules.md`](agent-rules.md) covers R1–R4, with at least one eval per
  rule.
- [`compose-catalog.md`](compose-catalog.md) covers catalog discovery and renders.
- [`compose-ui-builder.md`](compose-ui-builder.md) covers semantic design authoring.
- [`design-guidelines.md`](design-guidelines.md) covers catalog rule review,
  keyless prompts, shared results, evidence coverage and all four harnesses'
  current-context fallbacks, including catalog-only installs.
- [`rich-harness-integration.md`](rich-harness-integration.md) covers the viewer,
  interactive protocol features, reviewer agent, lifecycle summary, deep links,
  and complete text fallbacks from issue #18. Each case has a "no MCP Apps, no
  elicitation" column.
- [`token-budget.md`](token-budget.md) covers the routine render budget from
  issue #39: 3 or fewer tool calls, under 30 s, and no base64.
