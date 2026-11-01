# Compose UI Builder evals

Run these prompts in at least two harnesses with this repository's
`compose-preview` plugin (which carries the canonical `compose-ui-builder` skill
and the hosted server), or `compose-catalogs` on a host with no shell.

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

### 2026-10-11, preview.coo.ee 3.121.0, scripted by hand

- **Harness:** none. The prompts were followed step by step with a plain streamable-HTTP MCP client
  holding a UI Builder grant (`ui-builder-read`, `-write`, `-export`). This checks that the server
  supports each workflow and that the skill's instructions work against it. It does not check that
  an agent picks the workflow unprompted.
- **Canonical skills:** yschimke/skills `35e4587`, the last change to `compose-ui-builder`
  (#145, after #144).
- **Plugins:** this repository at `d20f78d`. Not exercised directly: no harness loaded them.
- **Server:** compose-preview-catalog 3.121.0 at preview.coo.ee.
- **Calls:** 81, each within 0.6–1.7 s, except `ui_builder_render_design_matrix` (6–11 s) and
  the 60 s decision waits. 2 errors, both noted below.
- **Images inspected:** 8. The editor view ×5, the device grid ×2 and the branch sheet ×1. Each was
  fetched with `inline: true` and looked at.
- **Follow-up issues:** none filed yet. The findings are listed under each prompt.
- **Designs:** `eval-login-1` (branches `-compact`, `-roomy`), `eval-wear-list-2` and
  `eval-textfield-probe`.

Tool sequences, omitting the `ui_builder_` prefix:

1. `create_design`, `apply`, `check_design` (dry run: `variant` rejected), `search_components` ×4,
   `check_design` ×2 (dry run: `singleLine` rejected, then clean), `apply` ×2, `check_design`,
   `view` (unsupported component); probe: `create_design`, `apply`, `view`; `view` with
   `renderer: "native"` (error), `check_design` (dry run), `apply`, `view`,
   `render_design_matrix`, `export`, `get_design`.
2. `list_catalogs`, `create_design` ×2 (the first was refused: `catalogUnavailable`),
   `check_design` (dry run), `apply`, `view`, `render_design_matrix`, `export`.
3. `get_design`, `list_comments`, `apply`, `view`.
4. `set_reference`, `compare_reference` (`nodeIds` → native → error), `compare_reference`
   (`renderer: "export"`).
5. Covered by the `check_design` and `render_design_matrix` calls in prompt 1.
6. `branch_design` ×2 (`revision: 5`), `apply` ×2, `compare_branches`, `pick_branch`,
   `merge_branch` (`dryRun`), `merge_branch`, `list_branches`, `check_design`, `view`.
7. `await_decision` ×29 (`revision: 6`, one at `waitSeconds: 0`, the rest at 60).
8. `set_implementation`, `find_design_for_pr`, `implementation_status`.

| # | Result | Notes |
| --- | --- | --- |
| 1 | Pass after fixes | The skill's `references/m3-catalog.md` gives `m3/text-field` a required `variant`; the server rejects it as undeclared, and outlined is now the separate `m3/outlined-text-field`. `ui_builder_check_design` passed `m3/outlined-text-field`, but `ui_builder_view` drew it as "Unsupported component", so only the editor view caught it. The catalog declares `singleLine`, but the Compose gate rejects it for `OutlinedTextField`, in a finding with no `nodeId`. With `m3/text-field` the check, view and device grid passed and the export had no diagnostics. No password text field exists in the catalog. |
| 2 | Pass | There is no `wear-m3` starter in the skill; `catalogRevision: "candidate"` is refused (`catalogUnavailable`), and the real pin from `ui_builder_list_catalogs` works. `screen-scaffold` › `transforming-lazy-column` › `list-header` + 3 `button`s render correctly on small and large round watches at 100% and 200% font. Export had no diagnostics. |
| 3 | Pass | Read the design (r4, filled button, no comments), then one `setProperty` → r5. The skill documents neither `setProperty` nor `deleteNode`; `ui_builder_apply`'s description names them. `ui_builder_view` with `selection` drew no selection. |
| 4 | Partial | Without Figma, the r4 render was attached as the reference (`facts`: `screen`, `pixelComparable`). `ui_builder_compare_reference` (export renderer) found one region, the restyled button (24, 248, 368 × 48 dp, 3.8 % of the frame). Layer alignment needs the native render, and preview.coo.ee has none for `m3-catalog` (`NO_NATIVE_CATALOG`). Because `renderer` defaults to native when `nodeIds` is given, the skill's step 5 fails as written on this host. |
| 5 | Pass | One check and one 12-cell grid (phone, foldable, tablet; light and dark; 100% and 200%). The grid showed the form stretched across a 1280 dp tablet, and the title nearly invisible in dark theme. The check reported neither: its contrast pass uses the design's own theme. |
| 6 | Pass | Two branches forked at the recorded r5, one numbered comparison sheet, and `ui_builder_pick_branch` → `ask-in-chat`. The person delegated the choice. A `dryRun` merge reported `"merged": true` before anything was written; the merge itself went r5 → r6 and archived the sibling. |
| 7 | Not completed | `ui_builder_await_decision` on revision 6 held each 60 s call and returned `timedOut` cleanly; no decision came in within 28 minutes, so the implementation step did not run. |
| 8 | Partial | Only the bookkeeping ran. With a stand-in PR URL, `ui_builder_set_implementation`, then `ui_builder_find_design_for_pr` found the design, and `ui_builder_implementation_status` said "no decision on this revision". No PR existed, so no PR previews were rendered or compared with the device grid, and no approved revision existed to judge against. |

The access grant also hit a server problem. Two pending `request_access` requests were lost
("no such access request") while preview.coo.ee restarted and reloaded its catalogs. A person who is
slow to approve during a deploy has to start over.
