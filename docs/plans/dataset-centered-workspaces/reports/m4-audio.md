# M4 first increment: local WAV Data workflow

Status: first Data increment locally qualified and independently accepted.
Exact runtime/test checkpoint: `2d5b8217967c6564b1b7089aef04be0b48c8c28a`.
The publication successor adds documentation/screenshots only; integration CI
remains the coordinating owner's gate.
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

## Independent review and clean evidence

The independent integration reviewer accepted exact runtime/test checkpoint
`2d5b8217967c6564b1b7089aef04be0b48c8c28a` on 2026-10-12, with no remaining
demonstrated P1/P2 findings. The reviewer independently ran three real PostgreSQL
custody cases (0.407 seconds; zero skips), and an actual Chromium discriminator
for invalid audio draft → text save and failed stale audio request → retained
newer text notice. The review identified those two editor-lifecycle issues before
publication; the owning fix and direct regressions are included. It also identified
nested rollback custody, now owned by `Metadata.on_rollback` without losing the
unknown-commit byte-retention contract.

Final audio-owner SHA-256:
`c96e70da0d969161412a69acefd1badf56f72ed451e20c81a7e0f5fd95298507`.
Final audio-editor SHA-256:
`445441b9ff4eb480cf26711b8a94eb55c1472164d7bb4ea3c68a1874f2093661`.

The final native Chromium gate is
`build/qa/workspace-audio/run-STgbvr/receipt.json`: source `2d5b821…`,
`dirty=false`, 13 passed checks. [Four original screenshots and their exact
manifest](../../../images/workspaces-audio/README.md) include saved source-channel
intervals, transcript/class text, the 390px layout and native 200% zoom. Zoom was
established by actual Chromium keyboard zoom with doubled device pixel ratio and
halved CSS viewport, after clearing viewport emulation. No horizontal overflow;
Tab reached the end-frame field. The reviewer inspected clean receipt and image
hashes separately from earlier dirty-candidate captures.

Earlier development checks revealed test-assumption errors, not suppressed gates:
connected-family 50/50 splits correctly refused a single component; restore
correctly required an absent destination schema; Chromium float positive sample
normalization needed the documented one-LSB comparison while frames/raw PCM stay
exact; reload needed the existing fresh-document barrier and explicit current
revision reselection after an intentional external edit. Final gates pass with
those owning semantics preserved.

## Runnable local demonstration

The authored populated demo was started at `http://127.0.0.1:8097/workspaces`,
with real HTTP 200 checked for the page and audio catalog. Choose **Current local
catalog**, then open **Authored stereo impulses.wav**. It contains a reviewed
channel-2 interval `[4000,8001)` and a frozen canonical release. The demo's record
ID is `4abdba399bb04667a1962e6c6e9e10ed`; its existing release is
`083c71a50fb59bbfdea233767febb69a54e5e4fd864cb038077a83f8647dd717`.
This separately seeded demo is distinct from the screenshot gate's retained IDs.

Launch command in this qualification environment (stop an existing instance on
that port before launching another):

```sh
TULDOK_DATABASE_URL='host=/tmp/tuldok-pg/socket port=5432 dbname=tuldok user=tuldok passfile=/tmp/tuldok-pg/app.pgpass' \
/tmp/tuldok-app-venv/bin/python app.py --data /tmp/tuldok-audio-demo-20261012 --port 8097
```

The PostgreSQL service and local app environment are prerequisites. Existing v1/v2
catalogs require the explicit quiesced schema upgrade described in the
[storage contract](../../../contracts/workspace-storage.md); this demonstration
created a new disposable schema-3 catalog and migrated no personal data.
