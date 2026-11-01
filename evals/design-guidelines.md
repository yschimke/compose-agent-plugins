# Catalog guidelines review evals

Run with the `compose-preview` plugin, which carries the canonical skills (or
`compose-catalogs` for the catalog-only case). Use the
[canonical checklist](https://github.com/yschimke/skills/blob/main/skills/compose-preview/references/design-guidelines.md).
Run each case in Claude Code, Antigravity, Codex and OpenCode. Also run with
no packaged reviewer, no MCP Apps/elicitation and only the catalog connection.
The checklist must complete in the current context when delegation is absent.

Use real renders for visual cases. Protocol fixtures may test missing evidence,
schema handling and stale records but must not be recorded as live visual
passes. Record the tool sequence and evidence, not just the final verdict.

## Cases

| ID | Setup and prompt | Pass condition |
| --- | --- | --- |
| G1 | Wear scrolling screen with an edge button revealed at the end: "Review this screen against its catalog guidelines using your own model." | Asked as surface `screen`, resolved from the preview's manifest entry (or passed explicitly only to correct it), and the request's provenance says so; applicable catalog rules; device and unrolled views inspected. Scrollable offscreen content and the initially hidden edge button are not reported as clipping/missing. A real clipping defect is still reported with rule/source/node evidence. No second provider call. |
| G2 | Mobile screen whose phone layout is stretched on a tablet: "Review adaptive behavior against the M3 rules." | Compact and expanded pictures of the same content inspected; relevant adaptive violations identified with catalog IDs and source links. A successful render/hash comparison alone is not a pass. |
| G3 | Review an isolated component, then a screen, with Wear rules | Component review does not claim screen-rule coverage. The screen request is asked as surface `screen` (manifest-resolved, or passed to correct a wrong entry), and all applicable asked rules are accounted for. Empty filtered rule lists are stated explicitly. |
| G4 | Remove the tablet/unrolled image, source evidence or renderer; include one certain violation | Reports partial coverage and unchecked rules/reasons alongside the certain violation. No invented picture, source fact, or `not_applicable` for missing evidence. Reads actual relevant pixels when available. |
| G5 | UI Builder result at revision N; edit to N+1 or change rule version while review runs | Old answers remain identified with N and its rules. Freshness is checked; the agent re-reviews or reports stale. Never writes old verdicts as N+1. |
| G6 | Server-homed design, current keyless prompt, writable review metadata | `ui_builder_record_guidelines` receives the prompt revision/version, all asked IDs and schema-valid verdicts with actual model provenance. Shared editor record is readable. No node/source changes and no `ui_builder_record_decision`. |
| G7 | Repeat G6 with read-only access, repo home, absent record tool, or structure-only prompt | Review still returns its coverage and explains why the editor record could not be saved. Detailed authorized discussion stays at the home. Missing visual/source checks remain unchecked. |
| G8 | Model suspects a small tap target or low contrast; measured accessibility evidence contradicts it | Measured facts take precedence within their stated limitations. Source/wrapper evidence is read before asserting a missing scaffold. Model warnings remain advisory. |
| G9 | Hosted catalog with `guidelines/result`, pending subjects, then an override render | Discovers/reads published data without requiring Gradle. Preserves original model/version/render identity and pending/unchecked status. Does not attach snapshot verdicts to overridden pixels or claim an unverified fresh result. |
| G10 | No OpenRouter key; then no dedicated guidelines tools | Uses keyless agent judgment first; when absent, inspects available rules/source/measurements/real renders manually. No credential request or provider spend. Missing rules are unavailable, not passed. |
| G11 | Requested CLI provider run with configured key, small cost cap | Bounded `compose-preview guidelines` run with explicit surface/rules. Reads its report, overlays and pending/unchecked coverage. Does not send a key as an argument or manually rewrite cached results. |
| G12 | Ask for G1/G2 with reviewer discovery disabled; repeat with only `compose-catalogs` installed | Same checklist runs in the current context. No failed-agent dead end, duplicate reviewer installation, mandatory optional `compose-review` plugin, or false viewer/delegation claim. Uses the harness's advertised tool names. |
| G13 | Glance Wear widget in an app module with no `ui-builder.guidelines.json` (wear-os-samples `WearWidget`, `WeatherWidgetRoundPreview`), current server | Asked as surface `widget`, profile `wear-widgets`, from the manifest, against the default remote-compose + wear-widgets packs, and says so from the result's note; not the Wear Compose screen rules. The excerpt shows the mock widget's `WearWidgetDocument(background = …)` and its `@RemoteComposable` content. On an older server that asks for `guidelines`, passes remote-m3-catalog's `remote-catalog` file. A batch mixing the widget with a screen is split, not asked one rule set. |

For H8 in [rich harness integration](rich-harness-integration.md), add G1–G8
to the reviewer acceptance run. Review coverage must be equivalent in the
current-context fallback; image isolation is expected only with a reviewer.

## Recorded runs

No live guidelines-review run is recorded yet. Do not infer a host pass from
the existing reviewer discovery fixture or packaging validation. Record:

| Date | Harness/version | Skills commit | Plugin commit | Server/CLI version | Cases | Execution path | Result | Evidence/tool sequence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

Include model, catalog/rules version, reviewed revision/hash, inspected picture
identities, answered/unchecked counts, record freshness and any access limit in
the evidence. Catalog-only and no-viewer runs need complete text/file results.

## Presentation cases

- In an MCP Apps host, request a measured audit: use supported render details,
  return findings and evidence in chat, and keep measured checks separate from
  model guideline verdicts.
- Click Review design guidelines in an updated viewer: review the exact subject
  and overrides using the agent model; return coverage, freshness and findings.
  A sent request must never be reported as an audit result.
- Disable or reject host messaging: provide the same copyable prompt without
  starting a provider run or claiming delivery.
- Read a saved UI Builder review in the viewer: show model, rules version,
  answered/asked and unchecked counts and findings; preserve stale status and
  distinguish no record or denied access from a pass.
- Record a UI Builder review: link the canonical editor and identify Issues,
  actual model and revision; a failed save must remain unsaved in the summary.
- Use OpenCode, CLI or an older static card: provide equivalent text, real
  artifact links/paths and a concrete follow-up prompt; invent no launch URL.

These are behavioral cases, not claims of live host verification.

- Review a server-homed design through a non-interactive or chat-only client:
  keep detailed findings in server comments when authorized, and return compact
  verdict, coverage and home/thread links. If posting is unavailable, report
  the limitation rather than copying design discussion into chat.

## Hosted connection recovery cases

- Ask to audit `remote-m3-catalog` in a workspace containing only preview tooling:
  discover the hosted catalog and use its published previews/data. No repository
  clone, local project registration, Gradle or cloud environment setup is needed.
- Have the host reject the first tool call with an expired Compose Preview
  connection: report that no audit ran and use the host reconnect action. Do not
  attempt repeated `request_access` calls to repair host OAuth credentials.
- Have the reconnect browser report `Unknown client_id`: explain disconnect/remove
  and re-add for a fresh registration, without inventing redirect URIs or tokens.
  Retry the review only after reconnection succeeds.
- Return a reachable server's `authorization_required` response instead: follow
  its advertised access-grant flow. A network/proxy error alone must not trigger
  an expired-grant diagnosis or a silent switch to local builds.
