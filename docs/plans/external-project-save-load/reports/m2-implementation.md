# M2 — Inert reconstruction, exact history and metadata publication

This report records the M2 qualification subject and results. The [plan](../plan.md)
owns current status; this is dated evidence, not a second status authority.

## Subject and outcome

Baseline: M1 `af276565fae9c08c1084d37d8937ba5d97599f17`, based on main
`133d53c0e2985a6559ba9cebd7d4a9f530051f06`. Main was re-read and unchanged.
Coding-Standards remains unchanged at
`5bce3110fc64d61ff8b4f79468184bd6295855d5`; the applicable principles and
workflow selection remain pinned in [baseline-and-standards.md](baseline-and-standards.md).

The tested/reviewed 226-file product subject is
[m2-tested-source-manifest.json](m2-tested-source-manifest.json), whose **file** SHA256 is
`7a8969d58594b4dc6f9412c5a31c77b2a13f59b807ad013084bfc351cdfde8f4`.
Its compact JSON content, excluding the terminating LF, has fingerprint
`cb070f64dfa11579ec3b759e6d2b02c12df59b6da2882f7e764489fe99dd3abe`.
The final staged whitespace check then caught one redundant EOF newline in the
new `project_data.py` file, which earlier unstaged checks could not inspect.
Removing that one newline produced an identical Python AST. No runtime campaign
was repeated for this formatting-only change. The final
[m2-source-manifest.json](m2-source-manifest.json) records that explicit delta and
has file SHA256 `ef2dc94d76d73fc11a45bcb06cf32dc5399d84370ef2a94dfbf6db800cfa9937`;
the exact old/new data-source hashes and AST parity are in the verification JSON.
Earlier receipts used content fingerprints; these are not mislabeled as file
hashes. Tests and CI configuration are separately identified in
[m2-verification.json](m2-verification.json) and the enclosing commit.

The concrete production result is one fixed owner composition for data and
histories, immutable material/runtime declarations, Study/Trial/Run/lineage proof,
producer history and artifact custody. Metadata mutations publish canonical
records and original-result receipts before SQL acknowledgement. Real SQL commit
failure retains the authoritative files and fences the projection. Legacy domain
routes remain unavailable in project mode before effects.

New/Open rebuild a fresh physical SQL projection without Dataset, live Runs,
producer workers or recovery constructors. Imported credentials, grants,
admissions and replay authority are absent. Historical namespaces, scientific
hash inputs, reservations/charges and lineage remain exact. Missing bytes have
explicit availability; consumers verify captured snapshots. Original wire bytes
which a legacy owner never retained are reported unverified rather than invented.

The 85 fixed project domain operations include existing modalities, authored
history, nonexecuting model/graph/recipe preparation, explicit local source
registration, bounded source references, current disclosure and rooted artifact
supply. Built-in preparation is fenced before its native probe until M3 owns
execution. Plain-text current records and manifests are tracked; binary sidecars
remain untracked. No source script is imported or executed on Open.

## Performed verification

Required-real environment: Linux/POSIX overlay filesystem, PostgreSQL 17.11,
Python 3.12.14, Node 24 and Chromium 151. Disposable authored fixtures only. A
separate cold database role cannot CONNECT to the source database. No local lab,
production data, external provider, training or GPU campaign was used.

| Boundary | Deciding evidence |
| --- | --- |
| Artifact/store publication | 42 artifact/store cases across the scoped campaign; verified fd snapshots, no-clobber/fsync/process boundaries, actual SQL rollback custody; targeted request-key/parser checks. |
| Shared session | Five actual PostgreSQL cases, including deferred COMMIT failure after canonical/artifact publication; the two initial fixture descriptor errors were corrected and only affected cases repeated. |
| Data/current source | 16 actual PostgreSQL cases after acquisition guards: all seven modality sources, annotations/rights/deletions, response/preference history, exact release variants, lost-reply compatibility and cold reconstruction. Existing native diagnostics were corrected and 21 affected native tests passed. |
| Material | 32 scoped material/package/evidence cases; targeted exact receipt/audit/agent-before-replay/built-in-probe guards; one actual opaque closure reader regression. |
| Historical proof | Six real owner cases passed on the first frozen subject. The failed composed-history fixture first needed multi-segment assembly, then exposed a real callback-shadow bug. After its repair, the composed proof plus two new classification/parser guards passed on the frozen corrected subject. Charges, producer inputs, original namespaces and cross-Study lineage survived cold SQL; active execution/grant/admission/replay tables remained empty. |
| Producers | 12 new real PostgreSQL cases, five affected live-owner regressions and targeted final checks: inert readers, exact payload custody, deleted source history, current authorization and credential classification. |
| Registration/resolution | Seven source lifecycle/import cases plus bounded reference reading; one actual rooted artifact-supply/replay/cold test. No imported root binding is activated. |
| Composition/cutover | Three complete-projection cases and all 11 M1 workspace tests passed after switching to the complete owner composition. |
| Public boundaries | Three real HTTP cases, including actual SDK/CLI/MCP, roles, stale binding/lost reply, missing artifacts, explicit supply, original disclosure facts versus new local permission, Git clone plus explicit untracked payload transfer. |
| Fresh metadata vertical | One actual HTTP case passed on the final 226-file subject: New, neutral source registration, captured model publication, external graph creation, actual nonexecuting recipe preparation, Study/Trial metadata, and cold exact material closure. Process launch and legacy Dataset/Run construction were forbidden throughout. |
| Browser | Actual keyboard/native authoring and cold reconstruction passed. The full receipt truthfully retained a responsive failure. A measured one-rule history-wrapping repair then passed the focused real cold-history gate at 390 and 1440 pixels, with zero HTTP/runtime errors and unchanged final source fingerprints. |
| Transport/controller | Finite registry/dispatch parity, current graph grammar, legacy grammar preservation, closed pages, thin SDK/CLI/MCP forwarding and controller stale/dirty/outcome checks passed. Named real gates preflight nonzero selection; optional MCP dependencies were present for its actual gate. |

The public summary and exact receipt locations are retained in
[m2-verification.json](m2-verification.json). Scratch evidence is under
`/workspace/scratch/tuldok-save-load-qa/`. Results are scoped to their source
subject. Unchanged valid evidence was reused; changed callbacks, guards, graph
grammar and CSS received targeted checks. No evidence-volume target or repeated
identical campaign was used. An earlier broad historical run during mutable host
source failed fingerprint checks and is excluded from acceptance evidence.

## Independent review and resolved findings

An independent reviewer read actual implementation and applicable standards,
then reviewed only the justified repairs/deltas against stable fingerprints.
Final source review: clear, no residual findings. This was read-only source
review and makes no independent runtime-execution claim.

| Finding | Resolution and evidence |
| --- | --- |
| Built-in material preparation could launch a probe. | Typed pre-execution fence before cache publication/owner preparation; actual PostgreSQL/Popen-forbidden regression. |
| Historical Run metadata exposed frozen holdout fields. | Shared live/inert public projection; current disclosure gates on exact documents, evidence and publication proof; cold current-permission refusal. |
| Historical audit/operation/acquisition shapes admitted unclassified content. | Exact finite owner variants and retained-fact binding. A residual permissive `studies.admit` result was refused: actual legacy admission persists reservations/audit, never that operation receipt. Admission proof effects now match exact real owner maps. No legitimate admission facts were removed. |
| Retained recipe reader overwrote its callback with a blob descriptor. | Separate reader/source variables; actual opaque preparation/closure and corrected cold composed proof pass. |
| UI treated native saved-selection `items` as a page. | Page checks limited to declared page actions; actual selection acknowledgement and controller regressions pass. |
| Unpinned references ignored observed hashes. | Current observed digest accepted with an unverified label; declared mismatches disabled and refused; actual unpinned import and mismatch negative pass. |
| Long cold-history hashes widened the page. | Measured 644–650px overflow at 390px; one history wrapping rule gives 375px document width without hiding content. Actual cold responsive gate passes. |
| Fresh external metadata lacked direct graph creation/current grammar. | Existing nonexecuting owner added to canonical dispatch; current graph schemas reused after legacy version construction, preserving old contracts. Focused contracts and fresh real HTTP vertical pass. |

The reviewer also cleared the narrowly added CI readiness/setup: job-owned cold
role/database, source CONNECT refusal, exact source subject, mandatory non-skipped
real MCP case and real Chromium gate. Existing broad discovery is unchanged.
These CI changes are configured, **not yet executed on the M2 commit**. A PR
synchronize event triggers them; the existing branch-push filter alone does not.

## Remaining scope and rollback

Live execution/producer starts, custody, candidate external publication and
runtime capture remain unavailable pending M3. Complete independent Save As,
working-file adoption/relocation/Git handling and mixed-catalog extraction remain
M4/M5. Early pure fork storage/data constructors are tested ownership seams;
their existence is not public Save As acceptance. Final A1–A9 acceptance remains
pending the complete implementation. No branch is merge-ready on this report.

If this slice regresses, close new project writes, retain canonical records and
payloads, and reconstruct only with a compatible reader. Never restore SQL over
canonical facts or delete orphan/published unique bytes as rollback. No user data
was migrated; no branch was merged or deleted.
