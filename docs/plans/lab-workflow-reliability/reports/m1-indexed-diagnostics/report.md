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

`git diff --check` passed. Actual PostgreSQL/custodian qualification is pending
the coordinated benchmark quiet-window release. Its executable fixture is
`tests/test_indexed_diagnostics_publication.py`: a fresh tiny metadata runtime
(`/usr/bin/true`, dummy 0.0 packages), captured SDK source serialized by the
harness before launch, real no-op child/custodian, injected publication copy
fault, cold recovery, exact inventory reads and unchanged accounting.

This is generic bounded diagnostic protocol work. Original actual lab diagnostic
failure bytes/path remain unavailable, so PUB-1 classification is blocked. No
captured Python producer execution, training, CUDA, physical operator,
scientific criterion or numerical acceptance is claimed. Full M1/T1/T2 acceptance
remains the root integration owner's decision after review and qualification.
