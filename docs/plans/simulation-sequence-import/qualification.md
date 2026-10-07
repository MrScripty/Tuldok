# Sequence import qualification and publication scope

The exact tested source is `08dfe25ecf8b8ac84778074c76306cd8d59e7203`;
complete local evidence remains at `cad08b652a7bcf5010afc2ab528297a601ff68d2`.
Those commits are preserved unchanged. This compact publication starts directly
from `309a87d753f97b245385f8d6db20353ab536a836` on
`feature/image-caption-exports`; it excludes generated evidence history.
[source-preservation.json](source-preservation.json) binds every changed code/test/
fixture blob to its exact tested identity. Publication commit identity is distinct.

Local final aggregate: **53/53 gates passed**, zero failed/blocked/stale,
**296 Python tests** and **24 real-browser scenarios**. Independent design review
preceded implementation; implementation and cross-repository reviews cleared the
native importer, actual boundary and all restored legacy consumer gates. The
isolated pinned consumer environment matched 44 version pins and seven source
hashes; tests prepared local datasets/collators without pretrained weights,
inference or training. Full logs, screenshots, releases and duplicate reports
remain local. Hosted exact-publication-head CI is tracked separately in the PR.

Producer contract is explicitly **unmerged Rheon draft PR 20**, exact
`fee7b4a139574f87b259796b1ba8698a41d31ac1`; upstream base is separately
`9cd4587a54befa61bdfddc8e35014bd3c34f02fb`. The vendored validator is unchanged
upstream blob `bcfff65366038fecbf898600fa0bec18626ce700`, SHA256
`063d17a3bbc92a27c26c0f5dd4588a9478091ebbf53ce0ccb818cee6a9393b98`.
Contract changes require coordinated review; no producer merge is assumed.

The small [actual fixture](../../../tests/fixtures/rheon_actual_fee7b4a/README.md)
retains unchanged output of exactly one clean capped Rust/Cargo 1.92.0 producer
execution: 16×8×4 constructor plus eight accepted steps, nine frames to 0.5 s.
Raw bundle files total **526,264 bytes**: run.json **7,313** and frames.jsonl
**518,951**. Fixture directory including its README/receipt totals **529,032 bytes**.
There are no large generated datasets, binaries, downloaded environments, frozen release
ZIPs, screenshots or repeated logs in this PR's additions. Existing base history
is untouched. Historical local paths in the raw manifest are producer provenance,
never consumer input paths or commands to execute.

The actual selected-file UI/API import initially produced one draft record with
unknown rights. Explicit review/history controls, protected trajectory/constructor
family boundaries and normal frozen release were exercised. Independent archive
inspection preserved both original raw files and all **29,664 native f32/f64
values**, exact metadata/index/time/dt/stamps/provenance and hashes; the trajectory
stayed one split unit. Actual and source-derived synthetic trajectories share their
initial-family boundary and cannot leak across splits. Synthetic fixtures retain
separate labels/placeholders and are never represented as the actual pilot.
The recorded actual browser test never invokes the exporter or another simulation.

Bounds remain exactly nine frames/16×8×4 cells, 64 KiB manifest, 2 MiB frames,
256 KiB line, 3 MiB HTTP envelope and 40 MiB selected sequence bundles. Named
MAC shapes/dtypes/units remain separate; pressure is the last accepted interval
projection. Validation precedes atomic Dataset-owned publication. No conversion
to images/cell-center vectors, frame-level splitting or broad 3D editor was added.
Imports remain unreviewed until explicit human review; technical validation grants
neither rights nor training qualification.

Scope is fixed all-fluid constant-density carrier and represented-fraction donor
transport. It does not qualify free surfaces, two-phase inertia, material calibration,
multidirectional accuracy, performance, training quality or a training model/consumer.
Main stays frozen at `2fc4a46f12d73a0fa467d5482f68edb83d6df6af`.
This is a separate draft: no merge, retarget to main or manual CodeRabbit request.
