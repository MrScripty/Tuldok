# Canonical A: actual CPU SDK and cold qualification

The actual canonical A source path passed at frozen host `4b68c51` on the explicit
`0b15b611ead55bd5fa6f2f7bbcc56870f6e9f9f60f2192d989e7473ef8af1826` CPU
snapshot. This is a new project, Model and finite Study. Historical authored A
versions and Runs remain unchanged. No canonical UI, fresh-package, B execution
or physical qualification is claimed by this receipt.

The [SDK/cold receipt](examples/e2-canonical-a-sdk-cpu.json) has SHA256
`8f655132472a8c828c82ec24b2fb7de9f0af1797dc82830068e339cc38b91d2f`.
It records one ordinary owner-granted SDK admission, all 32 public whole-hash
downloads, independent numerical/source verification, service/catalog reopen,
identical Model/composition/Study/Run/common evidence and all 32 cold downloads.

| Identity | Actual value |
| --- | --- |
| Catalog | `1139df50423642f0b5f579aa4b26bc8b` |
| Project | new canonical project retained in the receipt |
| Run | `610afd2bb09b4c1588b23a628d5756d3` |
| Study | `8d6428412c4148b3ad7df7f501cd90f4` |
| Trial | `3ee2b31d381f4d32840355be6b4cb2ec` |
| Model | `3a127bd4a572c8ff1fe5eb5e49e9e4b11f5d10c6749829092f611ee9a60808c8` |
| Full composition | `67a28c7765f6762ec32f5d3f6da9b8de79cb795401d50ef69c12e4ce23808c77` |
| Actual canonical Release | `8952f10c7878c758c40f8db329f68263716dfeb6c43196e0e66c1a77253db459` |
| Context | `afb25d4ee59a2a1a998eeafe9b65be9683e89ab3729de527dcfc81a1ea28476c` |

Source discovery and authoring were inert. A normal owner created and published
the configured Model, prepared the trial and granted its exact composition to
the agent. Model initialization was explicitly `initial_scale=0.125` and
`initial_offset=-0.25`; trainer controls were learning rate `0.1` and 64 updates.
The SDK performed one admission and inspection/download operations, with no
local producer fallback or implicit grant. It passed the real public graph wire
shape guard fixed in this host commit.

The real reviewed/frozen Release contains both train members and the fixed
validation member, with exact native arrays, provenance and derivation retained.
The new source closure captures the accepted SDK `94e17b5f...`, inference source
`15f6bc0d...` and acyclic inference contract `d60b9369...` in both provider and
recipe inventories. The producer `bcd80126...` and independent stdlib oracle
`573f142d...` were frozen before this Run. The expected context identity came
from the independently fetched public Run artifact receipt, never from hashing
the artifact under test as its own expectation.

The [independent oracle result](examples/e2-canonical-a-independent-oracle.json)
checks the actual Release/source proof, train-only normalization, analytic state,
all 64 validation values at each checkpoint and reference MSE. Its maximum
retained replay error is zero, maximum weight error `1.1102230246251565e-16`,
and maximum analytic prediction error `2.220446049250313e-16`.

| Actual optimizer update | Independently retallied reference MSE |
| --- | --- |
| 16 | `5.756206595554737e-4` |
| 32 | `4.560536716183977e-7` |
| 48 | `3.613229441027695e-10` |
| 64 | `2.862695293846856e-13` |

The Run completed and drained with no error, exit code zero, `go_received`,
`spawn_closed`, `echild` and `drained` true. It started at 23:43:59.079759 UTC and
finished at 23:44:18.265496 UTC on 2026-10-15. The runtime worker reported
`main_elapsed_seconds=0.019024402998184087` and peak process RSS
`277557248` bytes. These measurements describe this execution; they are not a
hard memory quota or a sandbox claim.

There were 21 immutable captures totaling 238,193 bytes and 32 outputs totaling
36,542 bytes. The captured runtime has 21,119 files and 881,709,420 bytes.
[Actual accounting](examples/e2-canonical-a-accounting.json) verifies all four
resource dimensions and the Study/trial/actor/epoch/key/material/request/Run
binding: one settled attempt, 197 admitted wall seconds, 4,495,421 retained bytes
and 6,216,933 peak staging bytes. Run, grant, consumption and reservation counts
were each exactly one after cold reopen. The normal runtime reserve was unchanged.

Two earlier disposable preparations remain preserved. The first stopped at an
owner-only graph operation before creating any Model, grant, reservation or Run.
The second exposed the SDK's fabricated top-level graph Project assumption;
read-only durable inspection established zero Runs, reservations and consumptions
and one unused grant. The real public shape was corrected and independently
reviewed before this fresh third catalog. No uncertain admission was retried.

Canonical native UI/public selected queries, retained fault/access/restore tests
and an actual P5 package/fresh consumer are subsequent required gates. The main
integration lead owns the separate `50502c0...` common A/B catalog and all merges;
that runtime has not been executed by this worker.
