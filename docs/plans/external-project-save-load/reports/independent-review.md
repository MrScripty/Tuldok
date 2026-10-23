# Independent plan review

Reviewer: independent read-only agent `/root/independent_plan_review`, 2026-10-22. One author integrated the collected findings. No reviewer product/document writes, application/catalog execution, local lab inspection, migration or publication occurred.

## Complete review subject

- Tuldok code: `133d53c0e2985a6559ba9cebd7d4a9f530051f06`.
- Coding-Standards: `5bce3110fc64d61ff8b4f79468184bd6295855d5`.
- Original complete `plan.md` SHA256: `7ba5a682fe9e64c0ef17d0aadfc3497813f9cf17041608fb6add0899d676bdbe`.
- Original `reports/baseline-and-standards.md` SHA256: `5a7bc63d5e2b1aa69fb4225b44721602740f3054a26a552eae150c2f5f4453fa`.

The reviewer read the complete plan and cross-checked actual Projects/metadata, app composition, Workbench/Preferences, Models/Pipeline, Studies/lineage, Runs/Access, candidate preparation, runtime and extension closure against current Planning, Architecture, Persistence and Verification requirements. The initial verdict was **revise three material gaps, then targeted re-review**.

| Finding | Source / reason | Author disposition |
| --- | --- | --- |
| R1 — High: replacement lifecycle | Current `app.py` binds one Dataset in `make_handler`; Open/New/reload could otherwise bypass Close, detach active owners or misroute old requests. | Added process-wide workspace controller, opaque project binding/session generation per request, exact pinned dispatch and Close/drain/unknown-cessation gate before replacement. T6/T8 cover delayed old reads/mutations, concurrent tabs, active jobs and failed switching. |
| R2 — Medium: editable files | Inventory hashes plus rejection/validation alone did not provide a usable path for intentional script/note edits. | Added explicit reviewed `adopt_working_files`, inert adoption context when drift prevents Open, retained prior captured versions/tombstones and a prohibition on recomputing immutable evidence hashes. T6 includes positive edited working files and negative immutable corruption. |
| R3 — Medium: direct owner population | `preferences.py` directly writes judgment history; `candidate_packages.py` composes prepared files/snapshots/material/Trials/receipts; runtime snapshots and extension readers own retained identity closure. | Added concrete family/disposition table, finite milestone path groups, M2 historical/metadata integration and M3 direct-writer integration or pre-effect unavailability. T2/M3 cover judgment rationale/review/history, candidate preparation and runtime/extension closure. |

The reviewer found the canonical-text/disposable-SQL authority, inert historical evidence, namespace-preserving fork, artifact manifests and stopped extraction direction coherent and source-supported. The full architecture probe and claim-directed evidence apply the standards substantively. `Planned` was adequately separated from implementation authority by explicit no-start language; no runtime acceptance or migration authority follows from it.

## Revised material and targeted review

- Revised `plan.md` SHA256: `3bd7e87f305bdff06c44dd9ac5168b3cfc0ac95f90b7f1b55c0e738985d1c674`.
- Revised `reports/baseline-and-standards.md` SHA256: `67a0d17727c1467cc1c979c0147462156c47a257dd134ffff6be3bbee9071911`.

Targeted re-review confirmed all three material findings resolved, with no blocking findings. The reviewer identified one nonblocking M1 bootstrap detail: define the controller's no-project-open binding so initial New/Open does not require an existing project UUID. The author added an explicit authenticated `no_project_open` state, installation/session generation, local root-selection authority and atomic transition to the project binding; project-specific operations are unavailable before selection.

The reviewer separately confirmed that narrow closure against final `plan.md` SHA256 `d6d3832a494a44aebae15bed20748a6d5b90dfa98919d315a179abae02d60b4d`; the baseline report remains `67a0d17727c1467cc1c979c0147462156c47a257dd134ffff6be3bbee9071911`.

**Final result: independent plan review clear; no unresolved findings remain.** No denied, pending or uncertain action blocked review. Adding this report, validation evidence or ledger bookkeeping does not change the reviewed plan/source subject. Only findings with changed semantic content were re-reviewed; no identical complete-review campaign was repeated.

This review is evidence about a documentation proposal. All product A1–A9 remain prospective; no implementation or runtime validation is claimed.
