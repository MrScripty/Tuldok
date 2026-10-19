# M6 source review candidate

Base: `2bf1d4035510003c6bbcc84d94b578a7ee753d69`, private branch
`feature/lab-field-comparison-20261019`. Root owns integration, CI and common
plan/ledger. This report records source readiness, not acceptance.

The distinct read-only `runs.compare_scientific_evidence/1` operation accepts
exact ordered completed Run and/or attached publication-result Ref operands,
retains owner-verified private arrays only inside the evidence owner, and returns
bounded field-point diagnostics, scalar compatibility, missing coverage,
immutable Model/material/Trial references, owner timings and explicit unknown
memory/criterion states. Existing comparison and evidence contracts are unchanged.
The existing Runs page and lineage comparison action select and display this
operation with exact pins, tables, narrow-width styles and stale/session fences.
Canonical behavior is documented in `docs/contracts/scientific-comparison.md`.

Local pure checks passed: five new Python comparison/compatibility/selection
cases, three existing model/publication contract-pin cases, new controlled Node
comparison controller cases, existing field controller regression, Python
compilation, Node syntax checks and `git diff --check`. Local logs are under
`build/qa/m6-source-review/` (ignored QA outputs).

Actual HTTP/DB/browser sources are implemented and pending execution while the
M4 quiet measurement matrix owns CPU attribution. The fresh fixture uses the
actual runtime-capture, Model/material, grant, finite Study admission and retained
read owners. Its tiny runtime contains `/usr/bin/true` and dummy packages and is
not runnable Python. Test setup explicitly authors synthetic terminal arrays and
custody receipts; no producer executes and no runtime/custody/scientific claim
is made. Production `_load`, `_extension_context`, publication, array and HTTP
verification remain unchanged. Full execution results will be recorded after
this source review boundary.

No owned scientific per-case metric/criterion Ref exists in the retained profile,
and the user's actual lab pair/acceptance criterion remains unavailable. T7's
qualified pass/fail criterion, lab-specific improvement and real runtime/training
qualification stay pending. Diagnostic point subtraction and byte custody do not
satisfy those claims. No producer/profile/schema migration is included.
