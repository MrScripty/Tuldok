# Extension-system issues and dispositions

## I1 — PR62 design alone is not production evidence

- Severity: high for product activation; no blocker to the plan.
- Evidence: pinned PR62 D4 identifies documentation design and future P1–P6 work.
- Owner/boundary: registry/model/evidence/Run implementation owners.
- Disposition: E2 requires accepted P1/P2/P3 and P4 generic field evidence; E4 package
  claims require accepted P5. P1 is now accepted; current remaining prerequisites
  are tracked in I7. No implicit prerequisite implementation in extension slices.
- Verification: actual source/qualification receipts before dependent slice admission.
- Revisit trigger: PR62 integration or implementation changes these seams.

## I2 — Live Coding Standards MCP unavailable

- Severity: informational for documentation provenance.
- Evidence: no callable standards tool is exposed in the drafting environment.
- Owner/boundary: documentation integration.
- Disposition: adopted dcc56f26 source and actual template used; retained prior MCP
  record is historical only. Do not claim a fresh consultation or upgrade.
- Verification: source/template structure and independent plan review.

## I3 — Executable extension runtime/numerical/cost gate remains pending

- Severity: high for X2/X3 activation.
- Owner/boundary: qualified captured CPU runtime and model/evidence owners.
- Disposition: E2 real producer/consumer/custody/cost gate; capability stays unavailable
  until it passes. Fixtures cannot close physical-model or unsupported runtime claims.
- Verification: exact captured runtime, actual checkpoints/probes, independent oracle,
  receipt-backed publication, measured selected profile bounds and cold inspection.
- Prerequisite evidence: PR68 qualifies the existing captured CPU/pressure producer;
  PR69 retains actual scalar checkpoints/probes and its independent frozen oracle.
  Neither ordinary external-recipe preparation implements the E2 model/evidence path.
- Revisit trigger: accepted P3/P4 integration or profile/workload incompatibility.

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
  witnesses passed; E4 complete retention/package qualification remains pending.

## I6 — SDK and host need one complete validation authority

- Severity: medium drift/dependency risk; root and independent review.
- Owner: extension contract; SDK/host are consumers.
- Disposition: E1 canonical data-only schemas and optional validator requirements/
  lock; E3 exact source-captured copies/hash/corpus conformance. Existing
  jsonschema4.26.0 closure is separately provisioned. Missing validator reports
  unavailable without importing app/DB/Torch or installing at startup.
- Revisit: unsupported keyword, divergent interpretation or new schema consumer.

## I7 — Accepted inspection and remaining executable prerequisites

- Owner: lead thread01a13f2b-3678-73df-8bce-2f57a04de00b for all merges/shared files.
- P1 PR66 merged as8673509; original E1 browser/HTTP inspection PR64 merged as
  91c5e96 after exact-head lifecycle/catalog/workspace CI and independent review.
- New snapshot routes remain owner-only/unregistered. Negotiated snapshot agent
  projections need explicit registry/CLI/MCP contracts and qualification; none are
  inferred from P1 negotiation support. Legacy project operations stay v1-only.
- E2 requires accepted P2/P3/P4. P2 PR70 at1678a4c is Verifying; generic P3/P4
  evidence/views remain unavailable. E4 requires accepted P5 export/fresh inference.
- Actual CPU/runtime/pressure and authored scalar-A producer preparation is retained
  in PR68/69, separate from host activation. Pressure physical result remains0/16;
  recurring pressure-CNN checkpoints/probes and protected test are unavailable.
- Current light baseline styles are reused. Shared dark model/evidence UX remains
  the lead's P3 concern; original E1 receipts do not claim it.
