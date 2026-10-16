# Extension-system issues and dispositions

## I1 — PR62 design alone is not production evidence

- Severity: high for product activation; no blocker to the plan.
- Evidence: pinned PR62 D4 identifies documentation design and future P1–P6 work.
- Owner/boundary: registry/model/evidence/Run implementation owners.
- Disposition: E2 requires accepted P1/P2/P3 and P4 generic field evidence; E4 package
  claims require accepted P5. P1–P6 implementations are now merged and qualified
  at their recorded sources; current remaining extension work is tracked in I7.
  Historical design acceptance alone is never implementation proof.
- Verification: actual source/qualification receipts before dependent slice admission.
- Revisit trigger: PR62 integration or implementation changes these seams.

## I2 — Live Coding Standards MCP unavailable

- Severity: informational for documentation provenance.
- Evidence: no callable standards tool is exposed in the drafting environment.
- Owner/boundary: documentation integration.
- Disposition: adopted dcc56f26 source and actual template used; retained prior MCP
  record is historical only. Do not claim a fresh consultation or upgrade.
- Verification: source/template structure and independent plan review.

## I3 — Executable extension runtime/numerical/cost qualification

- Severity: qualification boundary; the named CPU X2/X3 witnesses are complete.
- Owner/boundary: qualified captured CPU runtime and model/evidence owners.
- Disposition: PR76 retains actual canonical A source/cold/numerical/custody and
  finite-cost evidence on exact 0b runtime. The separate main 50502
  [canonical A](reports/canonical-a-50502-qualification.md),
  [independent B](reports/independent-b-50502-qualification.md) and
  [independent B cold consumer](reports/independent-b-actual-cold-consumer.md)
  also passed. B source/mask inputs, 32/64 checkpoints and raw/corrected stages
  were exercised under an unchanged 149-file application freeze. Its original
  tests-only oracle/recovery failures remain preserved; no admission retry or
  core numerical edit was used to close them.
- Verification: exact runtime/source identities, actual checkpoints/probes,
  independent oracles, retained whole bytes and finite envelopes are in those
  receipts. Runtime portable manifest and full composition descriptor are distinct.
  Synthetic fixtures still do not qualify physics, generalization or hardware.
- Prerequisite evidence: PR68/69 pressure/runtime and authored scalar preparation
  remain historical prerequisites, not substitutes for the later E2 path.
- Revisit trigger: a new runtime/profile/workload or changed numerical meaning.

## I4 — Documentation lifecycle and local integration

- Severity: medium; no application risk in this draft.
- Owner/boundary: primary documentation integration owner.
- Disposition: M0 is accepted; keep full product X1–X5 partial until their named
  implementation gates pass. Current E1 acceptance and next-slice state are in I7.
- Verification: adopted plan structural check plus lifecycle/authority review in executor.
- Historical M0 resolution: independent review/checks passed and local material commit
  `ccf01ae8d95340e29c89dfa8b39ba718aa9535ef` was verified; M0 Accepted,
  product Planned/partial and E1 unstarted. No push.
- Revisit trigger: new scope/authority or actual product slice admission.

## I5 — Old binary can silently project saved v2 as legacy project

- Severity: high consumer/version risk; discovered by independent source review.
- Evidence: Projects `_saved` JSON-loads rows and `get` iterates legacy groups;
  project document TEXT has no manifest-version gate for old readers.
- Owner: Projects/operator; Metadata only if an enforced storage gate is required.
- Disposition: old-binary/new-v2-store pairing unsupported. E1 proves new saved-row
  validation, quiesced pre-v2 backup/pairing and rollback into a new destination.
  Do not claim old binary refuses a saved v2 row; no live downgrade or DDL assumed.
- Revisit: requirement for machine enforcement or failure of actual restore;
  re-plan Metadata before v2 use. E1 reader/counterexample/quiesced backup/restore
  witnesses passed. Later [A/B stopped restore and retained-state proofs](reports/e4-ab-final-qualification.md)
  also passed, including original-source parity and complete A package/fresh
  reconstruction. These do not change the unsupported old-binary pairing or
  qualify the still-pending new agent-authoring path and final composed CI.

## I6 — SDK and host need one complete validation authority

- Severity: medium drift/dependency risk; root and independent review.
- Owner: extension contract; SDK/host are consumers.
- Disposition: E1 canonical data-only schemas and optional validator requirements/
  lock; E3 exact source-captured copies/hash/corpus conformance. Existing
  jsonschema4.26.0 closure is separately provisioned. Missing validator reports
  unavailable without importing app/DB/Torch or installing at startup.
- Current additional proof: six inert image/text/audio/mesh/points/volume
  descriptor families at `4f2c45a`, 8 focused plus 24 existing SDK/catalog cases,
  independently reviewed under SHA256
  `80e219b4b3e264e7653ad83409fd69e5b75cac0c66455051b8499b39b6564980`.
  Shared projections, authored bounds, malformed/dependency refusals and inert
  metadata fallback are covered; no new trainer, renderer or numerical meaning
  follows. Ordinary workflow regression remains its separate inherited gate.
- Revisit: unsupported keyword, divergent interpretation or new schema consumer.

## I7 — Accepted implementation and remaining current qualification

- Current status source: local composition `0150582`; final integration/CI authority
  is [PR78](https://github.com/MrScripty/Tuldok/pull/78). This documentation update
  does not claim that unpublished working source or this local composition is the
  current published head or has passed final CI. The lead owns serial integration.
- P1–P6 are implemented, qualified at their named sources and merged. The original
  E1 browser/HTTP inspection remains accepted with its narrow scope. Legacy v1
  grammar/projections and the old-binary/new-v2-store restriction are unchanged.
- Normal SDK admission already passed for canonical A and independently authored
  B using owner-prepared exact Trials. This is distinct from the still-unqualified
  ordinary-agent discovery/open/bound-model authoring path. Its published
  [PR86 candidate](https://github.com/MrScripty/Tuldok/pull/86), exact head
  `831ac7095790fcd0544c1afa15bf1c578a69a2c6`, is under revision-authority/receipt
  review. Earlier 12 focused cases passed in 67.377 seconds before the later
  corrections; they are historical observations, not current activation evidence.
  No fresh 50502 actual agent-authoring Run is recorded yet.
- PR76 at `6da68df` retains the exact 0b A source/package/separate-verifier and
  masked-consumer witnesses. Its three settled slots / 771 seconds / 55,405,809
  retained bytes / 102,988,554 staging bytes are unchanged, with no amendment.
  The distinct main 50502 A Study has three settled slots / 771 seconds /
  55,405,825 retained bytes / 102,988,586 staging bytes. Do not substitute one
  runtime/catalog receipt for the other.
- Main 50502 B actual source/cold and frozen `311431e` independent consumer
  passed. Original A/B stages, shared stopped backup/restore, cross-material grant
  refusal, current-access revocation, disabled/removed B selection, official
  HTTP/CLI/MCP, one unrelated classifier and 44 restored native captures passed.
  The final bookend SHA256
  `1589d5396ca45e5ec8758029288ea9a228d9f54e9b3ed7426ee748b3bb953cc6`
  keeps all original source state unchanged and restored 39 domain tables equal
  to the classifier-recovery boundary. [Shared matrix](reports/e4-ab-final-qualification.md)
  preserves its partial overall-acceptance disposition; the core's historical
  `rootless_retention_verified_disable_pending` state is not rewritten.
- The later canonical A package/fresh-verifier UI at `00865e9` is implemented and
  its two actual owner-browser journeys completed 56 captures. Final independent
  review SHA256 is
  `d26dbef42c29e3745686a388a43c33b2401822e8a56207c82f855bb433ceb1f2`;
  whole ZIP, selected verifier and all retained counts agree. B remains honestly
  unsupported for packaging. The late source proves 144 prior application files
  unchanged plus five explicit UI/backend deltas; it does not retrofit the earlier
  exact 149-file or later 148-plus-one proofs. Its [separate report](reports/native-external-package-evidence.md)
  is sealed at `6905fc8`; the real selected-read/revocation regression at
  `c0efd4f` has independent review SHA256
  `d5a61c41228ccb70b342058afecfceeca0bfd5b3464f9ed97d0cf401c032e4cb`.
  Serial composition remains lead-owned.
- Corpus `4f2c45a` closes the descriptor-envelope fixture obligation only (I6).
  The remaining functional qualification is the new ordinary-agent workflow,
  followed by sealed-proof composition, exact-head composed CI,
  independent review and lead acceptance. Overall E4/plan acceptance stays open.
- Pressure physical result remains 0/16; periodic pressure checkpoints/probes,
  protected scientific test, unsupported hardware and redistribution are not
  passed or silently added requirements.
