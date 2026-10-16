# Actual A stopped retention qualification

The opt-in witness is `tests/qualify_extension_retention.py`, frozen at
`6a53a17`. It uses the previously completed authored A fit and P5 package and
fresh verifier, with no new admission, completion injection, training or replay.
The application source is product `79088d8`.

The released source catalog is
`/workspace/shared/extension-a-50502-catalog-01`, catalog identity
`6538a60c4e944279b799299aa27d1d6a`. Inputs are the actual P5 charged receipt at
`/workspace/p5-qualification/field-a-charged-01/receipt.json`:

| Retained item | Identity |
| --- | --- |
| A fit Run | `87a0cfd1bfe6498793f9b46dc95b4950` |
| Package Run | `ba3c1e6bb17f4ddfab9b7905535fd2f9` |
| Fresh verifier Run | `3f52fb27c9a94f0ab4e816d83bcdea23` |
| Candidate | `59985dbb547d48a9834b5d3f932df31f` |
| Package ZIP SHA256 | `d386463952e85242e31b2c839b3e9b5e80002f87eed2f11a459c49d6d54f2d37` |
| CPU runtime manifest SHA256 | `50502c0ba923f3134073188efd55c20b0468c008b1bdfbdc87fd72ea830ffe3d` |

P5 explicitly released its catalog after stopping all owned processes and
settling all three Runs. The qualifier additionally claims the existing worker
locks and verifies completed/drained custody before copying. It never opens a
Dataset or creates a credential on the original catalog. Production
`backup_catalog` and `restore_catalog` own transfer, into an absent directory
and freshly created PostgreSQL database. The existing scientific restore
qualifier independently checks packed SQL values, sequences, schema identity,
every regular file, permissions and custody before restored-owner bootstrap.
This catalog contains 42 SQL tables and 20,999 regular files totaling
903,178,891 bytes. The runtime accounts for 20,804 payload files plus its
manifest; the manifest describes 896,562,621 payload bytes. Exactly three Runs,
three attempt reservations, three exact grants and three execution consumptions
are retained.

Inspection uses an empty project-root map; original external directories are
left in place and never copied. Subprocess creation and the Runs scheduler are
blocked throughout inspection and cold reopening. Current domain and negotiated
HTTP API2 reads check the selected native field and its exact P5 slice, recorded
16/32/48/64 update checkpoints with null epoch/fit/physical clocks, all retained
artifacts, frozen model/source/material, runtime files, finite Study charges and
the linked `fresh_verified` package state. Four selected artifacts also pass
whole HTTP downloads and segmented AgentClient whole-SHA reconstruction; domain
capture uses the same measured SHA and custody. Test population selection is
explicitly refused.

Only the restored owner issues and revokes credentials. Revocation must deny
selected fields, whole artifacts, segments, capture, package state, model and
recipe material, an already-created but unentered download context, negotiated
HTTP operations and whole HTTP download. A separate current inspector must
recover the exact retained meaning after cold reopening; the revoked credential
must remain unusable. All domain/grant/reservation/consumption tables, retained
files/modes/custody and the original source must remain exact. Restored access
actors, credentials and access audit rows are the only allowed SQL changes.

## Execution

**Passed** in 330.98 seconds at exact driver source
`6a53a17ab83a9520d3fad49616bcdceca85afec9`, driver SHA256
`24d5f24d863722b6c4911642a30909a35cd242f6417928a89af7e2cefef00e1e`.
The byte-identical [machine receipt](e4-a-retention-qualification.json) has whole
SHA256 `d9ca2c7678f5899122997b23c9cc1bb92399dd5044402f5fa394d8215ce7b7f4`.
It records exact preincident and final original-source parity, raw restored
parity, all 39 unchanged domain tables, 30 whole published artifacts, four whole
HTTP/segmented SHA proofs, eight denied revoked domain accessors, additional
HTTP 401 checks, null physical clocks, empty configured roots and cold current
inspection with execution/scheduling blocked. Independent read-only review
confirmed source and final receipt consistency without rerunning the witness.
The interrupted attempt is not a qualification pass.

Actual finite charges remain three attempts, 661 admitted wall seconds,
54,523,222 retained bytes and 101,399,545 peak staging bytes. These are the
original settled Study charges, not a new execution or a disk-size estimate.

Task-owned retained evidence is
`/workspace/p4-qualification/extension-a-retention-final01/`: `report.json`,
private raw baseline, `stopped-backup/` and `restored-catalog/`. The isolated
restored database is `tuldok_a_retention_04518263042a400fbbc6fd57713bf129`.
The original source catalog is released unchanged; all qualifier HTTP/Dataset
services have stopped. The old failed transfer and restored copy remain at
`/workspace/p4-qualification/extension-a-retention-attempt01/`; diagnostic log
`/tmp/p4-extension-retention-inspect01.log` preserves the interrupted read.

```sh
TULDOK_DATABASE_URL="$PRIVATE_LOCAL_POSTGRES_DSN" \
  /workspace/tuldok-runtime/bin/python tests/qualify_extension_retention.py \
  --source /workspace/shared/extension-a-50502-catalog-01 \
  --p5-receipt /workspace/p5-qualification/field-a-charged-01/receipt.json \
  --output /workspace/p4-qualification/extension-a-retention-final01 \
  --previous-baseline /workspace/p4-qualification/extension-a-retention-attempt01/baseline.private.json \
  --quiesced
```

The first transfer passed raw parity, then an owner-only root-list call was
correctly refused under the inspect credential. The driver now checks that call
in the owner scope. Diagnostic inspection on that restored copy subsequently
reached a cold package-state read when the shared PostgreSQL server disconnected
and entered recovery. The parent confirmed a 64 MiB Docker shared-memory limit,
a failed 32 MiB DSM resize and backend signal 11; it disabled parallel query and
maintenance workers and reloaded settings. No server restart, source write or
admission was performed by this qualifier. Failed attempt/output and diagnostic
logs remain retained. The final driver compares the source to the preincident
raw snapshot before creating its new backup.

## Limits

This qualifies retention of this actual private-QA A fixture and charged P5
package. The source A uses its authored project input; this witness does not
claim canonical Release input execution, SDK helper consumption, B execution or
provider disable/removal. It does not rerun inference, evaluate numerical
quality or establish physical acceptance, browser behavior, crash-interrupted
backup recovery, or compatibility with arbitrary adapters. PostgreSQL and local
filesystem storage are real; the execution blocks deliberately assert that
inspection remains inert. The new backup, restored catalog and isolated database
are kept for review. Credentials and DSNs are absent from committed receipts.
