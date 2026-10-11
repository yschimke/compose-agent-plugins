# Catalog guidelines review across harnesses

Install the default canonical `compose-skills` bundle along with the relevant
wiring plugin. Requested guidelines reviews use one
[checklist in yschimke/skills](https://github.com/yschimke/skills/blob/main/skills/compose-preview/references/design-guidelines.md),
packaged with `compose-preview` and linked from `compose-ui-builder` and the
optional `compose-preview-review` skill. The rule files stay in the catalogs;
this repository carries only harness routing and the reviewer allowlist.

Try: **"Review this Wear screen against its catalog design guidelines. Use
your own model, inspect the required views, and report unchecked rules."**
For mobile, substitute an adaptive phone/tablet screen. A hosted review needs
only `compose-catalogs` and the default skills, not Java or a local CLI.

## Execution by harness

| Harness | Install the checklist | Run the review |
| --- | --- | --- |
| Claude Code | `compose-skills@compose-agent-plugins` through the marketplace | Use `design-reviewer` from `compose-preview` when discoverable and delegation is allowed; otherwise follow the checklist in the current context. The packaged agent's allowlist contains local preview guidelines and hosted UI Builder guidelines tools. |
| Antigravity | Install `yschimke/skills/tree/main/plugins/compose-skills` by URL alongside the wiring plugins | Use the discovered reviewer or current-context fallback. Call advertised tools through Antigravity's server/tool interface, not Claude-prefixed names. Reinstall copied plugins and skill bundles to update them. |
| Codex | Enable `compose-skills` from this marketplace | Follow the checklist in the current context unless packaged reviewer discovery is confirmed. Skills and typed tools are sufficient; agent discovery is not a prerequisite. |
| OpenCode | Install `compose-preview` and `compose-ui-builder` with the Skills CLI; run `opencode-install.py` and register MCP as in [OpenCode setup](opencode.md) | Use the installed `design-reviewer` subagent when it is listed, otherwise follow the checklist in the current context. Use discovered server-prefixed tools, or the configured Code Mode interface. No hook or MCP App is required. |

A catalog-only install follows the current-context path in every harness.
Never install a second copy of `design-reviewer` in `compose-catalogs`; duplicate
agents conflict in Claude Code. The default skills make that agent optional.

## Capabilities and fallback

Discover the connected server's tools and schemas rather than assuming the
latest repository source is deployed. Local previews and hosted catalog
previews are different lanes; do not call local preview tools for a hosted
catalog just because their names look similar.

| Available capability | Route |
| --- | --- |
| UI Builder prompt/result tools | Read/reuse the latest fresh result, or judge `ui_builder_guidelines_prompt` with the agent's model. Record a requested result at the server home with `ui_builder_record_guidelines` when permitted. |
| Local preview prompt tool | Judge `preview_guidelines_prompt` with explicit `surface` and catalog rules. Keep preview verdicts separate from UI Builder records. |
| Published catalog `guidelines/result` | Read it with the catalog data-product tools. State its freshness and coverage; do not reuse it for override renders. |
| No guidelines MCP, CLI with a configured provider key | Use the canonical checklist's `compose-preview guidelines` command only for a requested provider run and budget. The reviewer permits that specific command, not unrestricted shell execution. |
| No provider key or dedicated guidelines tool | Inspect the catalog rules, source, measured checks and actual render images through available readers/tools. Report manual coverage and any missing evidence. |
| No required pictures/source or missing rules | Return a partial review and identify unchecked rules or the unavailable rule set; never call the review clean merely because findings are empty. |

The keyless path avoids configuring a second model provider: source, rules and
pictures are judged by the agent already doing the task. Provider checks can
send the same evidence to OpenRouter and spend its configured account's budget.
The checklist documents that choice; keys are never tool arguments or chat text.

The reviewer preserves code and design nodes. Recording requested guideline
results is review metadata, separate from human approval. Keep the existing
render/accessibility Stop gate unchanged; model guideline warnings are advisory.

## Validation status

The [guidelines evals](../evals/design-guidelines.md) define the behavioral
acceptance cases for all four harnesses, including current-context and
catalog-only paths. Packaging checks establish that the instructions and
allowlists ship; they do not establish that a host displayed pictures or ran a
model review. Record each live run there with exact commits and evidence.
Existing packaged-agent discovery observations remain in the
[harness matrix](harness-matrix.md); they are not guidelines-review passes.

## Results and review actions

Detailed findings follow R4: designs keep their discussion at the recorded
home, with home/thread links in chat. Only subjects without a recorded home
return detailed findings directly. Unavailable posting is reported as a
limitation, not permission to move discussion into chat.

Every host returns the verdict and coverage in chat with subject/revision,
freshness, model and evidence links. The agent uses the canonical checklist's
presentation rules; showing a viewer or requesting a review is not a pass.

| Surface | Presentation and next review |
| --- | --- |
| Codex Desktop / MCP Apps host | Request supported accessibility/layout render details for that audit. The server viewer can show measurements and overlays. Its Review design guidelines action, when available, requests a keyless agent review in chat; failed or unsupported messaging exposes a copyable prompt. For UI Builder subjects, Show saved review reads an advertised shared-result tool and displays model, rules version, coverage, revisions and findings. Missing, stale or denied records remain explicit. The compact verdict still appears in chat. |
| UI Builder in any host | Save the requested guideline result when permitted. Return the canonical editor URL and point to Issues for the shared model/revision result. Explicitly report unsaved results and stale coverage. |
| Claude Code, OpenCode, CLI and chat integrations | Return the same compact review and actual images/artifact links or paths; designs link to discussion at their recorded home. Offer a prompt naming the subject and missing checks when another review is useful. |
| Antigravity / static viewer | Show the real render/card and findings in chat. A viewer with the new review section provides a selectable request; copied older viewer assets require an update before they show it. |

Do not invent a browser route that runs an audit. The portable viewer packaged
here is pinned to a released server asset; an unreleased server change does
not update installed cards. Host messaging and visual results require a live
host check before claiming they work in Codex or another app host.
