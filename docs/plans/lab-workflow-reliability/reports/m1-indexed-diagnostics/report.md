# M1 bounded indexed diagnostics implementation

Owner: indexed diagnostics M1 delegated branch
`feature/lab-indexed-diagnostics-20261019`, worktree
`/workspace/Tuldok-lab-indexed-diagnostics-m1`. Implementation base:
`2bf1d4035510003c6bbcc84d94b578a7ee753d69`. Root owns independent review,
publication, integration and terminal worktree disposition. This private branch
is retained for that review; no remote operation or cleanup was performed.

The source implements the generic C2 addon under the explicit
`extension_field_policy_indexed_v1` policy tag. SDK and host share one bounded
index/record contract. The policy, recipe/material/context, addon digest and
opt-in host module closure bind it. Existing scientific manifests, capabilities,
legacy retained host-name sets and public evidence grammars remain unchanged.
The host proof stays private `_diagnostics`; exact original inventory readers
provide index/shard inspection and collection.

The new policy reserves all declared output maxima inside the existing profile
aggregate cap. It refuses impossible population, record identity, shard or index
reservations before compute. Complete mandatory records cannot be omitted;
optional omissions carry explicit count/range/reason. Existing scientific
verification runs first and an index cannot repair invalid scientific bytes.

## Evidence at initial source freeze

`pure-tests.log`: 53 tests run, 2 expected database-dependent skips, all remaining
tests passed. Command:

```sh
PYTHONPATH=tests:. /workspace/tuldok-runtime/bin/python -m unittest \
  test_indexed_diagnostics test_extension_field_evidence \
  test_extension_sdk_evidence \
  test_run_preflight_publication.FieldOutputPreflightTests \
  test_run_publication_http.PublicationContractCompatibilityTests -q
```

This covers supported SDK serialization, two deterministic shards, cold host
verification, exact inventory precedence over coherent worker forgery,
case/checkpoint/phase identity, byte/count/range/media/coverage failures,
scientific refusal precedence, opted-in admission bounds and unchanged closed
public contract validation. One intermediate test-only failure used an invalid
`selectors` argument for `runs.model_evidence/2`; the test was corrected to the
existing flat request grammar. No production contract was changed to pass it.

`git diff --check` passed. The executable PostgreSQL/custodian fixture is
`tests/test_indexed_diagnostics_publication.py`: a fresh tiny metadata runtime
(`/usr/bin/true`, dummy 0.0 packages), captured SDK source serialized by the
harness before launch, real no-op child/custodian, injected publication copy
fault, cold recovery, exact inventory reads and unchanged accounting.

This is generic bounded diagnostic protocol work. Original actual lab diagnostic
failure bytes/path remain unavailable, so PUB-1 classification is blocked. No
captured Python producer execution, training, CUDA, physical operator,
scientific criterion or numerical acceptance is claimed. Full M1/T1/T2 acceptance
remains the root integration owner's decision after review and qualification.

## Completed owner qualification

After M4's quiet-window release, the complete latest PR104 source
`1c9f01cb7e4adafd169dd56e95e02f0f5025b35d` was merged normally with the initial
implementation commit `28f61e8`, producing composed source
`f052fa7d93ee2df35f73afd28b565e1bac42183b`. Production diagnostic source did not
change during the qualifier fixture corrections.

`owner-roundtrip-final.log`: both actual PostgreSQL tests passed in 16.580 s.
Command (using the explicitly nominated private task-cluster DSN):

```sh
TULDOK_DATABASE_URL='<private task-cluster DSN>' PYTHONPATH=tests:. \
PATH=/workspace/tuldok-runtime/bin:$PATH /workspace/tuldok-runtime/bin/python \
  -m unittest test_indexed_diagnostics_publication -v
```

The negative test refuses an impossible population before graph creation,
process launch, Run, grant consumption or reservation. The positive test uses
actual Project/Model/Study/grant admission, harness SDK serialization, a real
drained/completed no-op child, frozen inventory and an injected output copy
failure. After reopen, real source, destination and cold exact-Ref semantic
verification pass. The original Run remains interrupted. Recovery is idempotent
under the same Ref; Run/grant/consumption/reservation counts, the reservation
document, conservative Study charge and original events remain unchanged.
An incorrect shard hash refuses. Public publication evidence still uses the
original closed projection.

`owner-roundtrip-receipt.json` retains actual result identity, exact index/shard
inventory hashes, coverage and accounting facts. The index is 948 bytes, shards
are 983 and 443 bytes, and all five declared ordinal positions are accounted for:
two mandatory and two optional records retained, one optional record explicitly
omitted for `capture_budget`. The successful Run was
`98d665737bdf44bfbb3fa0af44efa61b` in the fresh
`catalog_9173b8d7d0114555ab6798fb4ff4c523` schema. That exact recorded schema and
the negative-test schema `catalog_8e3d372a170f48a2944f0bd37e90fb95` were removed
after closing their catalog owners; the log records both removals.

`pure-tests-final.log`: 54 tests run, 2 expected database-dependent skips,
remaining tests passed. This adds a valid bound recipe addon/field-target and
host-closure witness to the initial group. No production source changed after
the successful owner qualification. `source-sha256.txt` records the final
production/test/contract file identities.

## Retained failed attempts and cleanup boundary

`owner-roundtrip-first.log` records two fixture setup errors: the configured
Project directory did not exist before Dataset construction. Dataset closed its
connection, but exact fresh schema identities were not registered before the
temporary manifests were removed. A read-only `pg_namespace` query afterward
observed newest candidate names
`catalog_9b3d1d36c0a2473d9a4e6a7a416653ec` (`xmin=9145`) and
`catalog_b423b373d5424501af8802943b4f7893` (`xmin=9146`), following an older
`xmin=9103` namespace. Temporal adjacency does not prove ownership. These
candidates were not opened, read or dropped. Cleanup is **not attempted and
blocked on exact ownership evidence**; root explicitly preserved this boundary.
No uncertain cleanup action was retried.

The corrected fixture records a fresh schema through Metadata before constructing
Dataset and registers exact cleanup immediately. `owner-roundtrip-second.log`
records a passing positive round trip plus a negative fixture error at the
existing immutable Project identity guard. It was corrected using a new
explicit Project ID. Both exact recorded second-attempt schemas were removed:
`catalog_bcd1d0b17e6340cdbccea964073b7d43` and
`catalog_9821a7d198e846369a511147fe6a982f`. The final run above passed both
tests. These were fixture mistakes; no production rule was weakened.
