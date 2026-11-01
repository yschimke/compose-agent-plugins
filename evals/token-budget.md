# Token budget evals

These evals check the token budget from
[#39](https://github.com/yschimke/compose-agent-plugins/issues/39). A routine render
turn:

- makes **3 or fewer tool calls**;
- finishes in **under 30 s** of wall time, from the prompt being sent to the
  reply ending;
- puts **no base64** in model output, either in the reply or in a tool
  argument the model writes;
- does **no doc reads or greps before acting**, so the first tool call is the
  render;
- shows **images only when the agent needs to see them**.

Run them with this repository's `compose-preview` plugin, which carries the
canonical `compose-preview` skill. Record the results as described in
[`README.md`](README.md), and add the wall time and, where the harness reports
it, the turn's input and output tokens.

## Setup

- A Gradle project with `@Preview`s. The recorded baselines used
  ComposeStarter's `ListScreenPreview`.
- `compose-preview` on `PATH`, at the version under test, and the plugin
  installed from the commit under test.
- A fresh session per case, unless the case says otherwise.

Count every tool call the model makes in the turn, including file views, shell
commands, skill or doc reads and subagent calls. Hook runs don't count.

## Cases

| ID | Prompt | Pass |
| --- | --- | --- |
| T1 | Cold render: "render the `ListScreenPreview`" in a new session, with no daemon running. | The first call is `render_preview` with the function name. There are 3 or fewer calls in total: the render, a look at the PNG, and in Antigravity with an older server, the card helper. The reply has the card or file path, a few bullets and the summary filled only from the result. There is no base64. Record the wall time; the 30 s target applies to T2, because a cold daemon includes a Gradle bootstrap. |
| T2 | Warm render: repeat T1's prompt in the same session. | Same call limits as T1, and under 30 s. |
| T3 | Edit, then render: "make the header say Hello and show me" in the same session. | One source edit, one `render_preview` and one look at the PNG: 3 calls, under 30 s. No `./gradlew`, clean, or build-folder deletion. A stale image gets at most one `force` retry, which makes 4 calls and counts as a fail with a note, not a crash. |
| T4 | Sweep: "check `ListScreenPreview` at font scales 1, 1.5 and 2". | Cells are compared by hash (`observe=hash` or the matrix equivalent). Only the cells the agent needs to judge are opened as images, and no more than one per cell. Either the sweep runs in the `design-reviewer` subagent, or its images stay out of the main context. Record the call count, but T4 isn't held to the 3-call limit. |
| T5 | Failure: "render the `NoSuchPreview`". | The first call is `render_preview`. The agent calls `list_previews` at most once, then reports the error and the nearest matches. It doesn't build a mock, grep the project or read docs. There are 3 or fewer calls in total. |

A turn that goes over a limit fails even if the render is correct. Write down
which extra calls it made, because they point to the fix: a server change (for
example auto-registration) or a skill change (for example "don't read docs
first").

## Separating render cost from agent cost

Run [`scripts/edit-render-bench.py`](../scripts/edit-render-bench.py) against
the same project and server. It times the edit → notify → render loop with no
model. When T2 or T3 misses 30 s, compare the result with the bench's warm
render time. If the bench is also over 30 s, the cost is the render. If the
bench is well under, the cost is the agent's steps.

## Results

| Date | Harness | Version | Server / CLI | Plugin | Case | Tool calls | Wall time | Tokens | Base64 | Result | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-09-27 | Antigravity (`agy`) | 1.2.12 | CLI 2.28.0 | #38 | T1 | about 12 | 2 min | not recorded | none | Fail: registered the project (`status`, `register_project`, `list_projects`), found the preview URI (`git grep`, read `MainActivity.kt`), and read docs, the harness-notes skill and the card helper | [#39 comment](https://github.com/yschimke/compose-agent-plugins/issues/39#issuecomment-5855864042) |
| 2026-09-27 | Antigravity (`agy`) | 1.2.12 | server 3.78.0 | #48 | T1 | 1 `render_preview`; other calls not recorded | 53 s | not recorded | none | Fail on time only: the card came from the server `embed`, and the summary came only from the result. The cold-start and warm split (T2) wasn't measured | [#39 comment](https://github.com/yschimke/compose-agent-plugins/issues/39#issuecomment-5856416678) |

The first baseline turn, in the 234d10dd transcript, took 6m44s. Its tool
calls weren't counted. The rows above were recorded before this eval existed,
so they are baselines, not runs of it. T2–T5 have not been run.
