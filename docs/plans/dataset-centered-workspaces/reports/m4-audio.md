# M4 first increment: local WAV Data workflow

Status: locally qualified; independent review and final publication in progress.
The admitted increment is Data import/playback/timed annotation/human review and
frozen export. It does not close the planned full M4 Pipeline/Runs recipe.

Branch: `feature/workspace-audio-data-20261012`, based on qualified M1/MB/M2
`6d939359d3cef2464c2aff990dd58d50c4f8d791`, with the complete reviewed PostgreSQL
schema prerequisite `126e677c8db6f9333491dfb9968f85b9c67ea482` merged without
selective replay. Root owns serial integration and the canonical plan/ledger.

The [audio contract](../../../contracts/audio-data.md) defines original-byte
custody, bounded PCM, source-frame coordinates, explicit human review and frozen
JSONL. Existing Data import, release and rights/history owners remain accessible.

The smallest workflow is: open `/workspaces`, choose **Current local catalog**,
open **Import / generate / release → Import WAV audio**, select a local PCM16 WAV,
open its record, listen/choose a channel and frame interval, enter a transcript
or class, add the interval, save with explicit human review, select the record,
preview a canonical release and export its original WAV plus JSONL.

Audio training and ASR remain unavailable. There is no hidden inference service,
model download, resampling or fabricated Pipeline/Run. The next audio increment
would be a separately admitted closed validation/export recipe with a real Runs
artifact preview; it must consume this contract rather than pretending the image
trainer accepts WAV.

Verification commands (disposable local PostgreSQL DSN required):

```sh
python -m unittest discover -s tests -p test_audio_data.py -v
node tests/browser_workspace_audio.cjs
```

The tests require FFmpeg/ffprobe as an independent WAV reader and Chromium for
actual browser decoding and keyboard workflow. They use only authored mathematical
impulses, never acquired/private audio. App runtime requires no new package.
No main merge, deployment or migration of personal data is included.

## Local qualification

- 10 audio Python tests passed against PostgreSQL 17.11: exact original PCM and
  half-open frame boundaries, invalid format/size/rate/frame rejection, review,
  stale edits, protected families, frozen provenance/JSONL, unknown-commit custody,
  confirmed nested rollback and complete backup/restore.
- 41 affected existing tests passed (10 Workbench, 19 release preview, 12 mesh),
  plus Workbench/mesh controllers and workspace fixture service contracts.
- 13 real Chromium checks passed, including browser decoder sample/frame checks,
  keyboard human review, repeated submit/lost acknowledgement, immutable WAV/JSONL
  export, stale revision refusal, fresh-document reload, invalid audio draft to
  existing text save, stale playback error ownership, Pause during preparation,
  narrow layout and genuine native 200% zoom. Source sample integers and frozen
  bytes compare exactly. Browser float decoding has a declared one-PCM-LSB
  tolerance because Chromium normalizes positive PCM values by 32767.
- A single authored maximal-byte probe imported 8,388,608 bytes (4,194,282 mono
  frames at 44,100 Hz; 95.108 seconds) in 0.100 seconds; exact-frame peak summary
  took 0.810 seconds and process peak RSS was 86,192 KiB. This is bounded local
  evidence, not a performance guarantee for other machines or codecs.

The accepted standards authority is Coding-Standards
`dcc56f26e884ade260770beceba2501d3746200d`: Core/router, implementation, frontend,
contracts/evolution, persistence, verification/oracles, accessibility, security
and commit workflow. Engine MCP is unavailable in this environment; independent
source review and the named executable evidence remain separately recorded.

No app database table or column was added by the audio owner. The separate
schema worker's reviewed v2→v3 constraint extension is preserved as a complete
merge, with retained v1/v2 migrations and backup semantics.
