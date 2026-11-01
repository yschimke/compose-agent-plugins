# Adoption: doors, one install, cookie trails

How a person gets from "I heard about this" to a working render, and what an agent loads on the
way. Read this before adding a default skill, a plugin, or a step to any front door or quick start.
It condenses the cross-repository adoption plan that `compose-ai-tools`, `yschimke/skills`,
`compose-ui-builder` and this repository were built to.

## Level 0: one door per intent

| Intent | Door |
| --- | --- |
| "Let my agent see my Compose UI" (the default) | <https://yschimke.github.io/compose-ai-tools/> |
| "Design a new screen with an agent" | <https://ui.coo.ee/start> |

Every README opens with one line pointing at the right door, then the one install below. Nothing
else goes above the fold.

## Level 1: one install per host

The same text everywhere; do not invent variants.

- **Claude Code:** `/plugin marketplace add yschimke/compose-agent-plugins`, then
  `/plugin install compose-preview@compose-agent-plugins`.
- **Codex:** `codex plugin marketplace add yschimke/compose-agent-plugins`, then enable
  `compose-preview` from `/plugins`.
- **Antigravity:** `curl -fsSL https://raw.githubusercontent.com/yschimke/compose-agent-plugins/main/scripts/antigravity-install.py | python3 -`.
- **Anything else, or no plugin system:**
  `curl -fsSL https://raw.githubusercontent.com/yschimke/skills/main/scripts/install.sh | bash`
  (the CLI and the two default skills).
- **No shell (Claude chat, Cowork, ChatGPT):** the `compose-catalogs` plugin, or the hosted MCP
  URL `https://preview.coo.ee/mcp`. Only the UI Builder door and [host setup](host-setup.md)
  mention it.

`compose-preview` is the only thing a coding agent installs: the `compose-preview` and
`compose-ui-builder` skills, the local `compose-preview-mcp` server and the hosted
`compose-preview-catalog` server. Docs never tell a coding agent to install `compose-catalogs`
as well. Host-specific detail lives in [host setup](host-setup.md), linked as "other hosts", never
inlined on a front door.

Then: **"Ask your agent to render one of your previews."** That is the whole onboarding.

## Level 2: cookie trails, not context

Further capability is discovered when it becomes relevant, never preloaded.

- **Next-step hints.** The `compose-preview` skill ends with an "Offer the next step" table: a
  signal the agent can see, and one sentence it may offer once, at the end of a reply. Preview CI
  and pull request review lead to the optional `compose-review` plugin; browsing everything leads
  to `compose-preview browse` or the VS Code extension; a running app leads to the simulator
  reference; designing a new screen leads to the UI Builder. Never more than one offer per reply,
  and never repeat an ignored offer.
- **Reference index, not preload.** Everything in a skill's `references/` is reached by a table
  row. No description mentions a reference-only feature beyond a few trigger words.
- **The setup skill** (`compose-preview-setup`) ends after the first render with at most three
  "what next" bullets.
- **Sites** have one "When you need more" section after the install, ordered by how often people
  need it: review and CI, the UI Builder, the simulator, then data products and MCP details.
- **Optional plugins** (`compose-review`) are reached only through these hints, never the quick
  start.

## Context budget

Every installed skill's description loads into every session, and a skill's body loads whole
when it triggers. Checked in review:

- A default skill's `description:` is at most about 400 characters: trigger words only.
- A `SKILL.md` body is at most about 12 KB; everything else goes in `references/`.
- Optional skills are installed on request, not by default.
- Skills that always load here (`harness-notes`) stay small, about 5 KB, and point at the
  workflow skills instead of repeating them.
