# Representative extension retention evidence

2026-10-15. Base: `6519f745d74bcf509bf4d7d4cc6a75e57547bb75` on
`integration/model-development-product`. Isolated proposal:
`feature/extension-retention-product`. Only the new retention test and this report
change; Projects, RuntimeSnapshots, Metadata, backup, Access and Runs are read-only.
The lead integration owner retains merge authority.

`tests/test_extension_retention.py` reuses the real v1 neutral external Project,
captured-model fixture and E1 v2 catalog files. Each case publishes model source,
prepares a finite Study, obtains an exact owner grant for an agent and admits its
Run through the ordinary queue. The actual neutral worker and descendant finish;
the retained custody receipt must report GO, drainage and ECHILD. No completed
Run, custody receipt, grant consumption or output is inserted as a DB fixture.
The output oracle is the fixture's original 55 input bytes, not a second producer
projection. The selected runtime is the existing neutral `system_python` profile.

## Observed contracts

- Selecting a new v2 snapshot with no extensions disables that context only.
  The original snapshot stays addressable with its exact references. Reusing its
  ID for changed enablement returns `conflict`; removing its provider makes
  current inspection `unavailable` without substituting another provider.
- Completed Run history, verified recipe/model material, captured source blobs,
  selected output download and custody bytes survive removal of the original
  provider and root. Rebinding the alias to a different directory does not read
  replacement source. New external/material preflight returns `unavailable`.
- Revoking the current credential denies Run/list, model, source, recipe, output,
  capture and previously created but unentered download contexts with
  `unauthenticated`/401. Cold reopen preserves revocation; a newly authorized
  inspector can still read the same retained bytes.
- A fully stopped catalog containing v1, enabled v2 and disabled v2 snapshots,
  published source, prepared trial, real completed Run and revoked credential is
  backed up and restored into a **new PostgreSQL database and new directory**.
  Tables, stored project JSON, files, file modes, material, output and custody
  bytes reconcile. No external root is configured or silently copied: an
  unselected root-only sentinel is absent from the backup. Restore and cold reads
  are exercised with subprocess creation and queue start set to fail. The single
  completion, one grant consumption and original events remain unchanged.

## Actual receipt

Final focused run: **3 passed, 0 failed, 0 errors, 0 skipped, 21.824 seconds**.
Python `3.12.14`, psycopg `3.3.6`, PostgreSQL server `170011`, catalog schema `9`.
The restore reconciled 42 tables and 33 file/directory entries. Temporary test
catalogs and the independently created restore database are cleaned afterward.

| Case | Actual completed Run |
| --- | --- |
| Current revocation | `b8e4ea5858f14d80bf27808b3ed7124b` |
| Disable/provider/root removal | `43bf2b03612149648c0c724c7b2f8063` |
| Stopped backup/new destination | `39958dd14b1d40f2a1f7db80e823e476` |

```json
{
  "test_source_sha256": "7da23c1eee2c0fd7d8075b62c42607380b7bc9f638687277a8d35b3dc85976c9",
  "neutral_worker_sha256": "06815b425a7722e0aa64d0c8739263fc2db371027b382d0c3326691305e1879c",
  "output_sha256": "54ae9355f214d827afd4ec287ff813d3af22683a52c10e9ed1ea62507cfa4d10",
  "backup_metadata_sha256": "3134d314ab32a62fa4dab0be5e250bb07dbe6463fb703d68b9b3df3b801b080c",
  "backup_recipe_material_sha256": "3f8af97780409aa3c61e333c262a9981cc2b7f35eff499819b016f4b40a03d47",
  "backup_model_sha256": "e69bb737d72e5ade0b0df984348d0252d6bd635205f5194ea5c7eccb61c46680",
  "backup_custody_receipt_sha256": "8072f717b5dc6cd0405291c6f118ab9b162a8e6ac6cce65db6f835f2ad1d15f0"
}
```

Reproduce with a disposable PostgreSQL DSN in `TULDOK_DATABASE_URL` and the
provisioned extension validator:

```sh
PYTHONPATH=tests /workspace/tuldok-runtime/bin/python -m unittest test_extension_retention -v
```

Full local receipts: `/tmp/tuldok-extension-retention-tests.log` and
`/tmp/tuldok-extension-retention-receipt.json`. No product-owner defect was found.
This is representative E4 retention evidence for current owners. It does not
close X5: scientific E2 execution, substantive A/B compatibility, captured runtime
closure and complete fresh inference require the actual extension fixture and
their separately admitted Runs/packages. Those gates remain pending.
