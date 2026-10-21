# Current-version interrupted retention restore

The existing T8 witness now proves controlled interruption and retry for the
combined current-version coordinator, timing, publication and client state. No
production repair was needed. This is an extension of the existing plan, from
merged main `8b1f78eb06c17e3dba2a73dc0acc9568e53ccc7e`.

## Exact qualification subjects

The initial source `0bbc6a7c4cd58dc0451d6ba6c0983193763e1f91` passed one focused
test in 17.614621813 seconds, with zero failures, errors or skips. Independent
review then requested backup permission checks at each checkpoint and the final
source/backup boundary, plus explicit sequence-fixture provenance. These were
added without changing a restore owner or fault seam.

The strengthened source `d02f034aa1bba6cd55dfd47ae44ebcb7014200a5`, tree
`68f147908523a65ce495f47392eada87273cbfaf`, passed independent reproduction:
one test in 17.012795836 seconds, zero failures, errors or skips. Its test file
SHA256 is `50ac2975b216052dc0d07248db9f21a8618f9cf096b22214c2c9a317c302d199`.
The independent source/reproduction review is clear; receipt SHA256 is
`92cc82aa677eeaca9496fe57af2997c8b45e95da58cba9fdb2778f5cb9df0700`.
The initial root pass is not relabeled as a run of the strengthened source.

Raw runners, logs, result/domain receipts and the preliminary/final review are
preserved byte-for-byte under `root/` and `independent/`. The
[manifest](evidence-manifest.json) seals their sizes, hashes, exact source
subjects and the small root-to-final assertion diff. Report-only publication
must preserve the qualified test bytes; current published-head hosted checks
and final report/source review remain merge gates.

## Real boundaries and independent state oracles

The existing fixture executes one actual neutral Linux custodian attempt,
drains it, faults original publication copying, obtains a real PostgreSQL
advisory-lock coordinator fault and performs explicit same-Run recovery. It then
stops the source, backs up raw schema 10 state and restores it into a separate database.

| Interruption | Observed safe checkpoint | Same-transfer continuation |
| --- | --- | --- |
| After real catalog population, before transaction commit | All 43 raw table states roll back to empty staging state; final destination absent; exact private restore marker retained. | Populate and restore original metadata/sequence state. |
| After metadata commits and the actual coordinator-journal file is copied and renamed | All raw tables/sequences equal source; copied inventory is a strict subset of complete original entries; final destination absent. | Verify existing entries and copy the remaining files. |
| After the actual final destination directory rename, before function return | Destination is published, staging absent, exact marker/tables/sequences/tree/POSIX modes retained. | Normal retry reconciles the completed result without overwriting it. |

At every checkpoint and after final cold reads, source bytes, source POSIX modes,
backup bytes, backup/catalog POSIX modes, source raw tables and source sequences
remain unchanged. The source values and inventories were independently captured
before restore; expected raw state does not come from a restore result or the
production timing summarizer.

The sequence high-water mark is explicit authored administrative fixture state:
`generation_jobs` starts at value 1/not-called and is set to value 20/called with
empty job-order rows. Its exact retained state survives committed transfer,
retry and cold reads. This is not a measurement of a real lab workload or proof
of arbitrary populated-sequence transactional rollback.

After reconciliation, actual application activation preserves the immutable
completed coordinator acknowledgement, original interrupted Run and events,
exact recovered publication Ref, and measured/incomplete timing records.
Authenticated current SDK and separate CLI processes collect identical complete
artifact bytes into mode 0600 files. All raw tables/sequences remain unchanged;
the compute-launch tripwire records zero calls during restore and consumption.
The fixture has one Run, one grant/consumption and zero Study reservations; it
does not replace the separate populated-Study acceptance evidence.

Both runs leave schema inventory empty and preserve the complete database-name
inventory. The independent reviewer also queried the exact emitted schema and
restored database names and confirmed both absent. The task-owned PostgreSQL 17.11
container was stopped after the serial test windows. No benchmark, broad local
suite, workflow rerun or old-version witness was launched for this extension.

## Retention decisions and remaining boundaries

The earlier real collection measurements remain the performance evidence. No
new performance comparison was run or inferred here. Explicit twenty-item batch
collection retains its scoped benefit; individual collection stays the default,
including the measured slower single-item batch controls. Preparation reuse,
installed-runtime mutation, other batch sizes and general workflow speed are
not qualified by this restore witness.

This qualifies controlled Python exceptions and retries, not host crashes, kill,
power loss or device/fsync durability. Partial copying here means a subset of
complete verified files, not a torn payload. POSIX mode bits are compared;
ownership, ACLs, xattrs and timestamps are not newly qualified. Full M2/M3/M5/T8
acceptance is not implied by these three boundaries.

The user's revised support policy remains authoritative: older project owners
perform their own one-time migration; no backward adapters or automatic
migration framework are added. Current-version schema validation, explicit
unsupported-version errors, backup/restore integrity and no replay remain
required. PUB-1 still needs its original real failed Run, custody, profile and
output inventory. SCI-1 still needs a real comparison pair, criterion authority
and environment/procedure. Neutral recovery evidence cannot supply those inputs.
