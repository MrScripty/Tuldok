# Versioned controls adapter implementation checkpoint

The finite adapter is implemented on a separate branch from PR42. This checkpoint qualifies implementation behavior with explicitly authored v2 fixtures; it does not satisfy actual-packet V2/V4/V5 acceptance. The original PR32 packet remains discoverable but not materialized locally. No producer rerun, fabricated native receipt or real-model success is claimed.

## Behavior and ownership

- Exact two-file v1 behavior, original reader, prepared metadata, protected family IDs and bundle bytes are retained. Explicit v2 requires exactly three files; version/file mixtures, unknown versions and malformed controls refuse before persistence.
- Pin Rheon main 2209012's controls validator and numerical reader separately, retaining their exact bytes except the controls reader's local import name. [Source hashes and attribution](producer-source.json) identify the Apache-2.0 upstream and local license copy. Two pinned readers preserve independent supported versions rather than broadening v1's build-command contract.
- Original controls bytes participate in the v2 trajectory identity, immutable bundle, origin metadata, batch receipt/recovery, frozen release and Runs report. Whole-trajectory/initial-family protection remains owned by the existing adapter and allocation owners.
- Data imports one or multiple trajectories with optional controls selection; server version dispatch is authoritative. Compact Data/Pipeline/Runs summaries show interval count and declared provenance, with details collapsed. Declaration is not authentication.
- Existing PostgreSQL immutable asset storage and the sole graph/run supervisor are reused. No schema, simulator, model or dependency installation is introduced. New controls storage adds only its bounded 64 KiB allowance; the 3 MiB request limit remains sufficient for the bounded base64 envelope.
- Both single and batch sequence routes now use the existing strict JSON request decoder. Independent review exposed duplicate-key/deep-recursion/nonfinite handling in the single route; a real HTTP regression proves typed rejection with no persistence and successful subsequent v2 import.

## Evidence at implementation handoff

Focused backend: 21 v2/batch/release tests and 13 retained sequence tests pass. Three additional v2 graph/run tests pass, including quiesced PostgreSQL backup/restore of exact record/source/release/completed-run bytes. These counts overlap other aggregate runs and must not be added as unique coverage.

Independent reviewer executed six initial v2 contract/custody tests, three v2 Runs tests, six retained v1 Runs tests and the added HTTP boundary test; both sequence controller suites passed. No remaining actionable source findings. Additional current-build-command and release-metadata corruption tests were read-reviewed and included in the backend aggregate.

Root Python compilation and all static JavaScript syntax checks pass. All test_*.cjs controller/artifact suites pass across the initial run and corrected-environment continuation. The rights-note browser preservation gate initially lacked the app Python/PostgreSQL environment and timed out; rerunning that gate and remaining suites with the required environment passed without source changes. Failure output is retained locally.

The existing browser harness passes unchanged recorded-v1 mode and `--authored-v2`, with actual Chromium, PostgreSQL and a working outbound-denial canary. V2 exercises missing-controls/mixed-version refusals, import/review/freeze, edited/cloned graph, execution/report, exact three-file download and restart. Receipts explicitly set `actual_v2_packet_acceptance:false`, use no native producer receipt and label authored source. This does not establish compatibility with the unavailable original PR32 frames.

A separate subprocess at clean pre-v2 PR41 cafe533 created a real completed v1 Run using retained actual fee7b4a bytes. Reopening that catalog with the v2 implementation preserved exact record, graph, completed Run, report, artifact manifest and release bytes. The [retention receipt](retained-v1-prechange.json) records source and hashes; no current-code reconstruction was substituted.

Full local Python discovery and ordinary hosted checks are run on the published implementation; terminal results and exact heads belong to the draft PR's validation record. This checkpoint does not presume they passed. No extra typed-language/lint build exists; registered static and behavioral gates remain enabled.

## Remaining qualification

Original frames.jsonl (518,951 bytes, SHA256 1f0cb462f6d145cdaca62a11d180c1bbcb0da6f8a7dae5369faf0be8f2dcdd28) and the packet handoff receipt still require supported retrieval. The exact failed operation and archive identity are in [readiness](readiness-20261013.md). Authored fixtures cannot close this gate.

A8 remains blocked on an available legitimate compatible gateway and real installed text/image model capability; [current read-only inventory](a8-runtime-20261013.md) found none here. No model was downloaded or inference success inferred from mocks. General 3D training remains excluded.

PR38–42 are preserved. The implementation worktree is retained under root/integration ownership for draft review. The disposable PostgreSQL fixture is used only for verification and will be stopped at handoff. No personal-data migration, merge or deployment is performed.
