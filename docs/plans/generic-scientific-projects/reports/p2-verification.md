# P2 lossless scientific fields qualification

Scope: generic scientific data custody and user inspection/review/freeze. No generator, training, physics/model accuracy or actor-authentication acceptance is claimed. Source branch: `feature/scientific-field-sequences-20261013`, based on P1 `46384fca`. [Bounded admission decisions](p2-admission.md) and [source hashes](p2/source-files.json) identify the local reviewed implementation. Hosted exact-head CI follows publication.

## Implemented behavior

Explicit import captures a saved project reference under its pinned root and requires the displayed observed SHA. A generic stored ZIP/NPY contract preserves exact float32/float64 bits, grid geometry, cell/MAC-face placement, time strings and producer stages. Original bundles live as ordinary immutable files; PostgreSQL schema6 owns catalog/review history. Schema1–5 identities are retained; upgrade is explicit and quiesced. Shared file publication preserves rollback and uncertain-commit custody without introducing a second store.

Data offers frame/field/axis/slice controls, physical coordinates and an exact numeric probe. Human whole-trajectory review uses the existing record and release owners. Canonical download and cold reader preserve source identity, repeated provenance and protected source/first-observed-state/declared-family groups. These groups are not proof of independent initial conditions.

## Observed workflow

- [Producer-neutral receipt](p2/neutral/receipt.json): rotated3×2×4 geometry, four field centerings and two frames;12 HTTP slices independently checked with NumPy. Five browser gates include stale-hash409 with no catalog write, review/freeze, cold original-byte read, restart and delayed import/newer clean-selection protection.
- [Native receipt](p2/native/receipt.json): actual two-frame32³ native capture, six fields;18 slices and12 arrays independently checked, with five original evidence files retained unchanged. Same five browser gates pass. Native unit declarations are explicitly unspecified.
- [Native observation](p2/native-observation/receipt.json), [decoded wire](p2/native-observation/decoded.json), [independent cold observation](p2/native-observation/cold-verification.json): pinned source/compiler/binary/raw identities and field semantics. Original scratch data remain at `/workspace/scratch/tuldok-science-probe`; reports do not claim the ignored historical lab packet was recovered.
- [Retained historical Run](p2/retained-runs.json): real schema3 Run upgraded to6, backed up/restored with exact old artifacts. New scientific source, review and history backup/restore is exercised by the storage suite.
- Desktop and390px screenshots: [neutral](p2/neutral/scientific-inspector-390.jpg), [native](p2/native/scientific-inspector-390.jpg). Root inspected narrow native output; selectors, original-value probe, geometry and stage remain readable.

## Verification and corrections

- Storage/publication/migration suite67 passed, including scientific restore and retained versions. Focused project17 passed. Scientific parser/service7 passed, including real HTTP import/inspection. Cold release6 passed with an external NumPy process and large legal metadata; independent spatial reader20 passed without skips.
- Existing workspace browser18 checks passed after final UI race fix (`run-8jQjNK`). Changed Python/JavaScript syntax and whitespace checks pass. Adopted standards plan-contract validator passes; no Standards Engine certificate or static type-checker claim.
- Independent source review:38 baseline checks and updated provenance-tampering test pass; no remaining product finding. Fixed contradictory frozen provenance and delayed import replacing a newer clean selection; browser regression covers the latter.
- Initial broad run exposed four audio worker failures caused by a new top-level server-only publication-helper import. Moving that import into admission restores the pinned worker dependency set; real audio training passes.33 integrity tests refused deliberately changed source identities while implementation was still being edited. Final stable-source full-suite result is recorded below when complete.

Full stable-source suite:696 tests passed in566.842s, three optional-reader skips. Separate qualified-reader runs pass20 spatial tests and6 scientific-release tests with no skips. Workbench controller, page-load and startup checks pass. Hosted exact-head CI: pending publication. P3/P4/P5 execution/actor/model work remains unimplemented by this milestone.
