# Compose UI Builder evals

Run these prompts in at least two harnesses with the canonical
`compose-ui-builder` skill installed from `yschimke/skills` and this
repository's `compose-catalogs` wiring enabled.

## Prompts

1. "Design a login screen with email, password and a primary button in M3,
   then give me the Compose code."
2. "Make a Wear OS list screen with a header and 3 buttons."
3. "Change the button to a tonal button."
4. "Make the home screen match this Figma frame: <figma.com/design/…?node-id=…>."
5. "Check the login screen is ready to show the designer, on phones and tablets."
6. "Try two headers for the settings screen, a compact one and a roomy one, and
   let me pick."
7. "Let me know when the designer approves it, then implement it in the app."
8. "This PR changes the settings screen: <github.com/…/pull/N>. Does it match
   the design?"

## Expected behaviour

- Acquire the `ui-builder-read`, `ui-builder-write`, and `ui-builder-export`
  grants when needed.
- Fetch a catalog summary first, then details for only the selected components.
- Create or copy a starter design, apply batched operations with a fresh
  operation ID and current base revision, and retry one revision conflict after
  refetching the design.
- Export Compose source and provide the browser design URL.
- For prompt 3, inspect the existing design before applying the focused change.
- For prompt 4, take the frame's screenshot with the Figma tools (never redraw
  it), say that the picture will be stored on the host and get permission, then
  attach it with `ui_builder_set_reference` (`density` from the export scale,
  `sourceUrl` the frame link) and record it with `ui_builder_set_links`. Read
  `facts` before editing — a region or another shape is not pixel-comparable at
  the default fit. Measure with `ui_builder_compare_reference`, apply the
  proposed `operations` a few layers at a time through `ui_builder_apply`,
  compare again until layers report `alreadyAligned`, look with
  `ui_builder_view` (`include: ["reference"]`), and report the remaining
  differences in dp and sp. When the reference tools are not advertised, say
  so and guide the person through **Frame, density and reference** instead.

- For prompt 5, call `ui_builder_check_design` and fix its findings by
  `nodeId` before showing anything. Then draw one
  `ui_builder_render_design_matrix` sheet (phone, foldable and tablet; add
  `fontScales: [1, 2]`), look at it, and name what breaks at the compact frame
  or at 200% font scale. Report the check's `summary`, the sheet link and the
  editor link; never describe the sheet without looking at it.
- For prompt 6, branch twice from the same recorded `revision` with
  `ui_builder_branch_design`, edit each branch, then call
  `ui_builder_compare_branches` once and show its one numbered sheet. Ask with
  `ui_builder_pick_branch`; on `ask-in-chat`, post the list and wait for the
  person's number. Never pick for them. Merge with `ui_builder_merge_branch`
  `dryRun: true` first.
- For prompt 7, give the link and revision, then wait with
  `ui_builder_await_decision` on that `revision` (a person's decision only)
  rather than asking in chat; an approval of an older revision does not count. Never record an approval on the person's behalf. After approval,
  implement the approved revision from `ui_builder_implementation_status`,
  render the affected `@Preview`s, and record the PR with
  `ui_builder_set_implementation`, adding `previewMatch` with evidence once
  compared.
- For prompt 8, find the design with `ui_builder_find_design_for_pr`, read
  `ui_builder_implementation_status`, render the PR's previews and compare
  them with the design's device grid. Say whether the PR implements the
  approved revision. Record `previewMatch` only when authorized to write.

## Results

Not run. Live service credentials and harness sessions are required.
