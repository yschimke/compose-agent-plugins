# Agent rules

These are firm product rules for every plugin in this repository. They also apply to the skills in
[`yschimke/skills`](https://github.com/yschimke/skills) and to the servers these plugins connect to.
A plugin, skill, tool or CLI change that breaks one of them is a bug. It is not a trade-off.

The rules describe what an agent must be able to do and how it must behave. Where the tooling
cannot yet support a rule, the gap is listed with its tracking issue. Until the gap closes, the
agent says plainly that it cannot comply; it doesn't work around the rule.

## R1: The agent sees what the user sees

For every surface a person can look at, the agent must be able to get the same view itself, as an
image plus structure, without asking the person to describe it.

| Surface | How the agent sees it | Gap |
| --- | --- | --- |
| Visual Editor (UI Builder canvas) | Document renders: `ui_builder_export_document`, export PNG/SVG | No view of the editor *as the person sees it*: viewport, selection, reference overlay, comment pins. [compose-preview-server#1114](https://github.com/yschimke/compose-preview-server/issues/1114) |
| Reference picture (Figma frame, mock) in the UI Builder | `ui_builder_view` with `include: ["reference"]` draws it as the editor does; `ui_builder_compare_reference` measures the design against it (regions by layer, per-layer move/size/font-size with `ui_builder_apply` operations); `ui_builder_set_reference` attaches one | The stored overlay does not yet record its *fit*, so a component crop attached over MCP is shown contained in the editor; an SVG reference is not measured server-side |
| `@Preview` renders | `render_preview` (local MCP or remote catalog) | The hosted catalog also returns a signed https PNG link ([compose-preview-server#1258](https://github.com/yschimke/compose-preview-server/pull/1258)); the local server returns inline base64 only, and a file path is [compose-preview-server#1109](https://github.com/yschimke/compose-preview-server/issues/1109) |
| Chat surfaces (Claude in Slack, Teams) | The https image link in each hosted result (`Image: <url>`, `imageUrl`, `contactSheet.url`), attached or linked | Live behaviour unverified: [#92](https://github.com/yschimke/compose-agent-plugins/issues/92), [compose-preview-server#1262](https://github.com/yschimke/compose-preview-server/issues/1262) |
| Source code | File read; `ui_builder_export` (`compose`) for a design's code | — |
| Native render | `ui_builder_render_native` (when configured); local previews render natively through the daemon | Not available on every deployment; the agent must say when it is missing |

Behaviour:

- Before calling a visual change done, the agent looks at the result on the surface where the
  person will judge it: the editor for a design, the preview for a composable, the native render
  when fidelity matters.
- When the agent cannot see a surface, it says which one and why. It never infers a visual result
  from JSON or source alone and presents that as seen.
- The agent never fakes a render. It doesn't hand-build an HTML, CSS or SVG mock of a preview,
  or an interactive imitation of one, and show it as the UI. Only output from the render tools
  counts. When rendering fails, the agent reports the failure instead of substituting a mock.
- What the agent looked at can be shown to the person. In Antigravity this is the preview card; in a
  chat surface, the https image link or an attachment made from it; elsewhere, a file path.

## R2: Typed tools with schemas, not raw JSON

Every operation an agent needs, whether to view, validate or edit, exists as a typed tool in both
the **MCP server and the CLI**, with a published schema.

- **Inputs:** every tool declares an `inputSchema`, and the server rejects arguments outside it.
- **Outputs:** every tool that returns structured data declares an `outputSchema`.
- **Documents:** the design format (`compose-ui-builder-document/v1`) and the mutation format
  (`DesignMutationV1`) are published as versioned JSON Schemas that any tool can fetch, not only
  the IntelliJ plugin. Tracked in [compose-ui-builder#320](https://github.com/yschimke/compose-ui-builder/issues/320) and
  [compose-preview-server#1114](https://github.com/yschimke/compose-preview-server/issues/1114).
- **Edits:** they go through validated operations (`ui_builder_apply`) that return the new revision
  and a way to view the result (R1).
- **Validation** is a tool of its own. Checking a document against its schema, its catalog pin and
  the export gate must be possible without saving (`ui_builder_validate`), and so must checking it
  for accessibility before a person sees it (`ui_builder_check_design`, which also dry-runs a batch
  of `operations`).
- **Hand-editing a design's JSON is a last resort.** When it happens, the agent validates before
  saving and re-renders afterwards (R1).

## R3: Every design has one canonical home, recorded in the design

A design lives in exactly one place:

- **server**, a `compose-preview serve` deployment identified by URL and design ID; or
- **repo**, a `.uid` file at a path in a repository (`ui-builder/designs/`).

The design records its home, and every export records the home and revision it came from. The
field is [compose-ui-builder#320](https://github.com/yschimke/compose-ui-builder/issues/320), and the server side
is [compose-preview-server#1114](https://github.com/yschimke/compose-preview-server/issues/1114).

Behaviour:

- **Edit at the home.** For a server-homed design, apply small batches of operations to the server
  so collaborators watching the editor see progress as it happens. Don't export the design, edit it
  locally and re-import it.
- **Temporary copies are allowed with conditions.** A local copy is fine for something the home
  can't do, such as a compile check or an offline experiment. When the agent makes one, it:
  - marks the copy as a copy, meaning its recorded home still points at the canonical store;
  - tells the person where the copy is and why;
  - saves it back to the home or discards it before the session ends. The end-of-session check
    reminds it.
- **Many edits on a copy isn't collaboration.** If a task needs more than a few operations, do them
  at the home.
- **Moving a home** (server to repo, or the reverse) is an explicit action the person approves. It
  updates the recorded home in both places and leaves a pointer at the old one.
- **Exports are artifacts, not designs.** Exported Kotlin, PNG or SVG carries a header or metadata
  naming the home and revision, and the agent never edits an export expecting the design to change.

## R4: Discussion stays with the design's home

- **A server-homed design's discussion is its server comments.** At the start of work the agent
  reads them (`ui_builder_list_comments`). It replies, acknowledges and resolves there, and uses
  `ui_builder_await_comments` to wait for a person. A person's approve or reject of a revision is
  recorded at the home too; the agent waits for it with `ui_builder_await_decision` rather than
  asking in chat.
- **A repo-homed design's discussion is the pull request or issue linked from it.**
- **Don't split the conversation.** Don't restate or continue a design discussion in a pull request,
  an issue or chat. Link to it instead (`ui_builder_set_links`). The pull request implementing a
  design is recorded with `ui_builder_set_implementation`, and the code side reads what it needs
  with `ui_builder_implementation_status`.
- **Before finishing,** the agent checks the home for unread or unacknowledged comments and reports
  them.

## Enforcement

Adoption is tracked in [#12](https://github.com/yschimke/compose-agent-plugins/issues/12).

| Where | What it enforces |
| --- | --- |
| Skills (`compose-ui-builder`, `compose-preview`: canonical in `yschimke/skills`, vendored into the plugins) | The behaviour in R1–R4, written as steps the agent follows |
| Server `initialize` instructions | A short statement of R3 and R4 for any client, including clients without the skills |
| End-of-session check (the opt-in `compose-preview` Stop gate, issue #4) | Unsaved temporary copies (R3) and unacknowledged comments (R4) |
| `evals/` | At least one eval per rule, run in two or more harnesses |
