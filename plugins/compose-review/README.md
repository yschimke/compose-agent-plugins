# Compose Review

Review Jetpack Compose UI pull requests by rendering base and head, diffing
them and checking catalog design guidelines, and set up GitHub Actions CI that
posts before/after previews on pull requests. It is optional: install it next
to the `compose-preview` plugin when you review UI changes or want preview CI.

Start at <https://yschimke.github.io/compose-ai-tools/>. This folder is generated from
[`yschimke/compose-agent-plugins`](https://github.com/yschimke/compose-agent-plugins);
install steps for each harness are in its
[host setup](https://github.com/yschimke/compose-agent-plugins/blob/main/docs/host-setup.md#install-per-host).

## What it contains

- The `compose-preview-review` skill: review a UI pull request locally or from a
  CI agent session, author an agent-opened UI pull request, and triage unstable
  previews.
- The `compose-preview-ci` skill: wire, repair or speed up the CI that renders
  previews and posts before/after comments, including fork pull requests.

Both skills are copied unchanged from
[`yschimke/skills`](https://github.com/yschimke/skills) at the commit recorded
in this repository's `src/vendor/skills/provenance.json`. The plugin has no MCP
server, no hooks and no agents; the skills use the `compose-preview` CLI and the
servers of the `compose-preview` plugin.

## Data it sends

Nothing by itself. The skills run `compose-preview`, `git` and `gh` on your
machine or in your CI, which send what those tools send.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
