# Neutral lab-workflow measured baseline

This Linux-only C4/T5 slice measures existing owners before any optimization. Production is
fixed at `96c2adebc3a46b9fe92b179097474e08474689c3`. The isolated benchmark
adds no cache, bulk endpoint, runtime installation, admission bypass or product
change. It copies deterministic neutral bytes through actual process custody;
it produces no training, numerical, CUDA or scientific acceptance evidence.

`tests/benchmark_lab_workflow.py` creates its own disposable PostgreSQL catalogs
and small Project/recipe/input fixtures. It populates terminal history through
real grants, admission, execution, drainage and publication. History cells are
0, 8 and 55 genuine completed Runs. A separate fresh-catalog supported workflow
measures preflight, grant, submit, completion and whole-hash collection together.
Each layout emits 327,680 bytes as one or twenty individually hashed artifacts.
The layouts have different deterministic input bytes and recipe declarations;
exact material equality is required within each layout, not across layouts. No managed Torch snapshot is copied. Only a fixture's recorded
new schema and temporary directory are eligible for cleanup.

For each artifact/history cell, three fresh sequential application processes
measure their initial call and two same-process repeated reverifications. Fresh
process does not mean OS or PostgreSQL page-cache cold: caches are not flushed.
Preparation, full capture, capture from an already held prepared representation,
Run list/metadata, retained source-proof reads and individual whole/16KiB segment
collection are measured separately. The held representation is an existing
within-invocation helper comparison, not cross-call reuse or a proposed cache.

Every successful measurement requires exact material identity across repeated
calls/process/history, exact captured input/source hashes, path-keyed retained
output inventories and final whole-artifact SHA256 equality. Read/preparation
cells have a process-launch tripwire and unchanged Run/grant/consumption/model
reservation counts. Additional separate fixture witnesses mutate and restore an
owned input/published payload, reject a wrong expected runtime inventory, revoke
a disposable inspection credential, and exercise partial failed selection.
Installed runtime bytes are never modified; its actual mutation/invalidation
case remains unavailable under this slice's constraints.

A separate genuine successful-compute/copy-fault Run retains its source and is
recovered on the same Run through the existing publication owner. Recovery,
result reads, repeated exact-key verification and recovered individual collection
are measured with a launch tripwire. Original outcome/events and settled
admission/accounting counts must remain unchanged. These measurements are
outside the fixed completed-history cells and do not imply science acceptance.

Raw receipts retain wall time, process/waited-child CPU, RSS snapshots/lifetime
high-water values, Linux logical/physical I/O counters, owner call/hash counts,
inclusive owner spans and actual HTTP request/declared body bytes. Application,
HTTP handler and client share a process; PostgreSQL backend CPU is excluded.
I/O includes instrumentation's own `/proc` reads. Inclusive owner spans overlap
and must not be summed. Body counts exclude headers and never retain credentials.
RSS high-water values are process lifetime values, not phase-local peak memory.
Small descriptive samples report min/median/nearest-rank p90/max without a
confidence, latency target, representative-lab or improvement claim.

Reproduce only against an explicitly selected task-owned disposable database:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:tests \
TULDOK_DATABASE_URL='<disposable PostgreSQL DSN>' \
python tests/benchmark_lab_workflow.py --out '<new evidence directory>'
```

The script refuses an existing output directory, records exact source/harness
hashes, Python/platform/cgroup/affinity/load/disk attribution, verifies unchanged
source/harness at finish, and saves raw cells plus descriptive distributions.
No credential values are written to evidence. Private worker control files stay
in the owned 0700 temporary directory with mode 0600 and are removed on cleanup.

Final measured results and exploratory harness-failure history are retained in
`docs/plans/lab-workflow-reliability/reports/m4-workflow-baseline/`. This baseline
alone does not complete T5 candidate/invalidation qualification, full M4, live
lab performance, or the plan's acceptance gates. Any future optimization needs
an explicit owner-scoped follow-up and paired evidence. Authorization, grants,
free space, readiness, mutable installed-runtime identity and scientific status
must remain current-owner decisions.

The frozen matrix completed successfully at harness `83d7e8f`, with all 18 read
processes / 54 cycles, six fresh workflows and both integrity/recovery tails.
Eight recorded schema/directory cleanup checks passed. See the retained
[measured results](../plans/lab-workflow-reliability/reports/m4-workflow-baseline/results.md)
and [complete cohort-qualified distributions](../plans/lab-workflow-reliability/reports/m4-workflow-baseline/qualified-distributions.json).
Three focused reporting tests passed. The original failed pilots remain separate.
