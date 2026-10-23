# Independent M3/M4 custody review

This is a scoped source-review record, not milestone acceptance. The review found
the issues below and verified their described source corrections. No remaining
finding is open within those targeted corrections. M3 Study execution still
needs its causal repair and actual qualification; candidate publication is being
implemented, M4 public/lifecycle acceptance is unfinished, and M5 is unfinished.
Approved-agent transport and original-host recovery through the actual public
clients also remain qualification gates.

## References and review boundary

- Main: `133d53c0e2985a6559ba9cebd7d4a9f530051f06`.
- Integration baseline: `c22e9d02c87938514a7a1c9b3b0532158008ca0d`.
- Coding Standards: `5bce3110fc64d61ff8b4f79468184bd6295855d5`, read from
  `/workspace/Coding-Standards-readonly`. Applicable material included
  `CORE-STANDARDS.md`, `STANDARDS-ROUTER.md`, `PLAN-STANDARDS.md`,
  `ARCHITECTURE-PATTERNS.md`, `SECURITY-STANDARDS.md`,
  `profiles/boundaries/persistence.md`, `workflows/planning.md`, and
  `workflows/verification.md`.
- Requirements: [the reviewed plan](../plan.md), especially canonical-before-GO,
  current local authority, original custody retention, independent fork identity,
  exact historical closure, and explicit unavailable boundaries.

The first complete M3 source review began with 232 matching product files in
`/workspace/scratch/tuldok-save-load-qa/m3-run-study-freeze.json`, file SHA256
`d31893bd6c6562869c0a1fd63942eba17a8931ea5c07c9012eecf77ca023624b`.
Later custody/M4 review was explicitly against an evolving tree with individual
file hashes. The separate 2,422-file custody qualification manifest,
`/workspace/scratch/tuldok-save-load-qa/m3-custody-qualification-source.json`, has
file SHA256
`5f82530d0b86610e4e3aa645f4359d45f8c5d0b844341d356d73264fd31e4694`.
Its runtime results apply to that captured subject, not automatically to later
changes.

The reviewer read source, relevant focused tests and recorded evidence; performed
file hashing and syntax-tree inspection; and did not execute application code,
tests, processes, catalogs, or migrations. No local lab was inspected. The only
reviewer-authored file is this report. No publication or commit was performed.

## Findings and source resolutions

| Finding | Consequence | Source resolution verified |
| --- | --- | --- |
| Lazy Run construction preceded request validation. | A stale/conflicting request could reach current-local recovery before rejection. | Construction moved into `Session.mutate`'s `invoke`, after exact receipt/body/CAS checks. |
| Commit callbacks still observed an open transaction frame. | Deferred Run wakes could append themselves indefinitely to the callback list being drained. | Metadata pops the completed frame before outcome hooks, cleanup and wakes; nested success still propagates callbacks to its remaining parent. Representative file cleanup and in-memory restoration callbacks were inspected. |
| Background canonical uncertainty did not immediately fence execution. | A replaced checkpoint followed by failed fsync could leave Session marked available after SQL rollback. | Background publication catches canonical uncertainty; Session retains recovery identity and becomes unavailable. Execution fences when Session is unavailable regardless of SQL outcome label. |
| Ordinary `execute` guards rejected approved external agents. | Public Run submission and Study admission could not reach their dedicated approval policy. | Those routes use `require_external_submission`; Study's canonical wrapper uses inspect only after that policy check. General Access execution restrictions remain intact. |
| Producer-only recovery checked custody too late. | Recovery could close the original store and release its flock before discovering an active/unknown producer. | All-family `has_local_custody` and quiescence checks precede store replacement. Original-host pending custody is also fenced. |
| Normal reconciliation ignored checkpoint CAS. | A stale same-binding request could drain work admitted after the caller's selected checkpoint. | Normal reconciliation validates the current checkpoint before effects; recovery-required reconciliation retains its separate last-acknowledged checkpoint rule. |
| Producer cancellation signals preceded canonical commitment. | Failed publication could still stop a worker or send provider cancellation without a durable cancellation fact. | Project cancellation prepares intent inside the transaction, signals only after acknowledged canonical and SQL commitment, and drains outside command locks. Legacy standalone behavior remains separately owned. |
| Save As supplied a zero-argument allocator to a three-argument callback. | Forking any editable record raised `TypeError`; an empty source could miss the failure. | Workspace now supplies the declared family/source/revision allocator signature. |
| Custody lookup filtered by current project UUID before physical root. | A valid UUID-changing checkout could hide unresolved original-host work on the same inode. | Lookup scans host-owned journals and matches physical root first; reconciliation refuses a retained/current project identity mismatch. |
| Original-cache promotion rotated the binding inside an ordinary execution response. | SDK and browser correlation rejected successful recovery as a transport failure. | Promotion preserves the same logical workspace binding. Workspace serialization, checkpoint CAS, exact replay and current authority fence delayed requests. Ordinary Open/switch/Save As still invalidate the selection generation. No concrete stale-request hazard was found in this scoped correction. |
| A fork could reactivate an unnamespaced v1 receipt by editing its archive list. | An original source key could replay against the destination using retained archived result records. | Active v1 receipts are refused whenever a fork overlay exists. Unforked legacy reading and archived historical receipt validation remain available; new writes use the v2 project namespace. |
| Disclosure history used the active replay-key index. | Save As retained source receipts but hid original Run disclosure observations and reasons from public historical results. | `ProjectHistory.disclosure_facts` now reads validated `operation_documents`, filters exact origin/Run, and leaves present disclosure permission to the separate current gate. |

The final disclosure correction was read at SHA256
`4cec697b7de96f4632c735de26b97c30c3bc306aa4700ad1d8ef328493519b50`.
Its focused test explicitly checks that the archived fact remains visible, the
active replay index stays empty, another origin does not receive the fact, and
the fact does not satisfy current disclosure permission.

## Sampled source identities

These identify the sampled files containing the reviewed paths. Where another
owner edited a module during review, targeted correction verification does not
claim full review of that owner's later changes.

```text
project_custody.py
17e3b76cc8ea5aff7863e75520a2cba9cef786bca78d5227d7b5da56c2ffe0b0
project_workspace.py
d0e85a90121a2242a0dea85d7061cb705001e136a45fc5cafcc3ec0d3f87da66
project_session.py
dee671d824433d67af68f24b17011196c86931f79de0eefb36e4d8afd8757503
project_execution.py
924faf003bcad64f7d1c154823af408b5a707a9d195d133b149c033bd51f5824
project_producer_execution.py
41a0e4dca2bb2059a82d91563eae2b9a28a11a87869a187c67a6c555de0ec4e2
project_history.py
4cec697b7de96f4632c735de26b97c30c3bc306aa4700ad1d8ef328493519b50
project_fork.py
b886ce2380285a10f879ae46c8883b5c0872481557c8c600eb5e2296185f0745
project_fork_composition.py
69d052062e7c7e824f0ffb4133ff05c8c4b5236da46976c627883a91a43c08f8
project_material_fork.py
349fc4619fa49d9df3e52a3d042d2f5523d0b8acdacfd675bc11b8bca53bf481
project_data_fork.py
3f49c244eba627e35d6f0fc9e7384c665113de6e2afa2219593440b7350ac911
project_files.py
b092994dd2f23995c86e098cbde7180a4d0e88e660ddda999bc6d9552f6af0e1
metadata.py
7bb728cab2068a415eb071191b61241dc2886a765044d9588487f4e8b8d11d86
```

## Validation limits and remaining gates

The lead reported nine targeted controls passing with the disclosure correction,
and two pure Session controls passing for the fork/v1 receipt refusal. These are
reported test results, not reviewer-run campaigns. Existing recorded Run,
custody-crash and workspace-provider results retain their own exact source scope;
none is upgraded here to current complete-product acceptance.

Still required are the causal Study execution repair and its actual gate,
approved-agent public transport qualification, actual client correlation for
original-host recovery, completed candidate/runtime effect ownership where
advertised, and M4 public/lifecycle/independent-edit qualification. M5 extraction
is outside this acceptance claim. No full-suite rerun, CI result, merge readiness,
or scientific/model-quality claim is implied by this source review.
