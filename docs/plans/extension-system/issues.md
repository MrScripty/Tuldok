# Extension-system issues and dispositions

## I1 — PR62 production seams are not implemented evidence

- Severity: high for product activation; no blocker to the plan.
- Evidence: pinned PR62 D4 identifies documentation design and future P1–P6 work.
- Owner/boundary: registry/model/evidence/Run implementation owners.
- Disposition: E2 requires accepted P1/P2/P3 and P4 generic field evidence; E4 package
  claims require accepted P5. No implicit prerequisite implementation in extension slices.
- Verification: actual source/qualification receipts before dependent slice admission.
- Revisit trigger: PR62 integration or implementation changes these seams.

## I2 — Live Coding Standards MCP unavailable

- Severity: informational for documentation provenance.
- Evidence: no callable standards tool is exposed in the drafting environment.
- Owner/boundary: documentation integration.
- Disposition: adopted dcc56f26 source and actual template used; retained prior MCP
  record is historical only. Do not claim a fresh consultation or upgrade.
- Verification: source/template structure and independent plan review.

## I3 — Product runtime/numerical/cost evidence remains pending

- Severity: high for X2/X3 activation.
- Owner/boundary: qualified captured CPU runtime and model/evidence owners.
- Disposition: E2 real producer/consumer/custody/cost gate; capability stays unavailable
  until it passes. Fixtures cannot close physical-model or unsupported runtime claims.
- Verification: exact captured runtime, actual checkpoints/probes, independent oracle,
  receipt-backed publication, measured selected profile bounds and cold inspection.
- Revisit trigger: actual runtime availability or profile/workload incompatibility.

## I4 — Documentation lifecycle and local integration

- Severity: medium; no application risk in this draft.
- Owner/boundary: primary documentation integration owner.
- Disposition: after reviewed local documentation commit, mark M0 accepted; retain overall
  product plan Planned/partial with E1 as the next separately authorized slice. Never mark product X1–X5 satisfied from docs.
- Verification: adopted plan structural check plus lifecycle/authority review in executor.
- Revisit trigger: final documentation review and verified local commit. No push.

## I5 — Old binary can silently project saved v2 as legacy project

- Severity: high consumer/version risk; discovered by independent source review.
- Evidence: Projects `_saved` JSON-loads rows and `get` iterates legacy groups;
  project document TEXT has no manifest-version gate for old readers.
- Owner: Projects/operator; Metadata only if an enforced storage gate is required.
- Disposition: old-binary/new-v2-store pairing unsupported. E1 proves new saved-row
  validation, quiesced pre-v2 backup/pairing and rollback into a new destination.
  Do not claim old binary refuses a saved v2 row; no live downgrade or DDL assumed.
- Revisit: requirement for machine enforcement or failure of actual restore;
  re-plan Metadata before v2 use. Product verification remains pending E1/E4.

## I6 — SDK and host need one complete validation authority

- Severity: medium drift/dependency risk; root and independent review.
- Owner: extension contract; SDK/host are consumers.
- Disposition: E1 canonical data-only schemas and optional validator requirements/
  lock; E3 exact source-captured copies/hash/corpus conformance. Existing
  jsonschema4.26.0 closure is separately provisioned. Missing validator reports
  unavailable without importing app/DB/Torch or installing at startup.
- Revisit: unsupported keyword, divergent interpretation or new schema consumer.
