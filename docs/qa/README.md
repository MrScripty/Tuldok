# QA outputs and retained inputs

Run the complete registered offline gate set with an installed pinned consumer
environment:

```sh
python scripts/qualify_text_classification_local.py --python /path/to/consumer-venv/bin/python
```

The runner prints a fresh directory under `build/qa/qualification/run-*`.
Each gate receives its own output root. Logs and generated screenshots, session
JSON, test ZIPs and manifests stay directly in that gate's output directory;
nothing scans or copies old report trees or earlier runs. `--report-root` accepts
only ignored `build/` or `output/` containers. `--resume` requires an explicit
existing run directory and reuses passing results only for unchanged source and
complete, hash-matching artifacts within that gate's original output subtree.
`--only` records the chosen scope; it does not certify the entire registered set.

Standalone browser tests use fresh `build/qa/SUITE/run-*` directories. Set
`TULDOK_QA_OUTPUT_ROOT` to another ignored build/output directory or an external
output directory. Authored source/fixture/report paths are rejected as destinations,
including paths aliased through existing symlinks. CI uploads `build/qa/**` as
temporary artifacts. These are optional downloads, never repository inputs.

The UI replay also uses relocated inputs and ignored outputs. To compare with
the frozen legacy application, supply a checkout of its exact main commit:

```sh
git worktree add --detach /tmp/tuldok-frozen-main 2fc4a46f12d73a0fa467d5482f68edb83d6df6af
TULDOK_LEGACY_ROOT=/tmp/tuldok-frozen-main node docs/plans/workbench-ui-qualification/capture.cjs
```

The replay verifies application sources against development `309a87d7` and the
legacy checkout against frozen main before launching either application.

Ordinary screenshots are JPEG quality **85**. Fixture images and original
pixel/hash-dependent image bytes remain lossless PNGs; new JPEG hashes describe
new captures and do not replace archived original PNG hashes. Generated PDFs,
archives, logs and screenshots belong in ignored output or separate downloads.
No PDF or generated artifact bundle is added to Git.

## Necessary inputs

- `tests/fixtures/native-caption-release`: nine unchanged files, including four
  normalized PNGs, canonical manifest and split metadata. Used by native-caption
  HTTP/SQLite and browser integration checks. All original hashes remain pinned
  in [the historical index](historical-artifacts.json).
- `tests/fixtures/workbench-ui`: authored blue-book PNG and asset JSONL for the
  UI replay. Source-image and manifest bytes remain exact.
- `tests/fixtures/qa/inherited-gates.json`: the original 43-command registry;
  runtime results are not inputs to the runner.
- `scripts/prepare_caption_fixtures.py`: the retained authored fixture generator;
  output must be a fresh path in ignored build/output.

Simulation-import draft PR20 is a separate branch. Its 529,032-byte actual Rheon
fixture, source/evidence commits and public head are untouched by this cleanup.
Its synthetic fixture stays separately labeled. The local cleanup/sequence/mesh
integration also routes both sequence browser suites and mesh inspection through
validated fresh QA directories; all ordinary captures use JPEG85. The actual
sequence output override is validated and cleared in aggregate children so their
outputs stay in the corresponding gate. No training, model download or new
simulation is needed for repository hygiene or this integration.

## Historical evidence retrieval

The unchanged reachable ancestor
`309a87d753f97b245385f8d6db20353ab536a836` contains all original report bytes.
Cleanup removes generated outputs from the current tracked tree without rewriting
history. Authored review/verification prose, including the sole recorded real-Pumas
observation, remains accessible. Its historical relative artifact links refer to
the archived baseline tree. The compact index records original source identity,
relocated input hashes, compressed oracle hashes and small outcome summaries.

Retrieve any original byte stream or recreate the complete historical checkout:

```sh
git show 309a87d753f97b245385f8d6db20353ab536a836:docs/plans/annotated-caption-import/reports/fixtures/native-caption-release/manifest.json
git worktree add --detach /tmp/tuldok-qa-history 309a87d753f97b245385f8d6db20353ab536a836
```

Historical probes and compressed oracle cases can be inspected or reproduced in
that checkout using their retained source and commands. Old real-runtime observations
are preserved evidence; they do not request new inference or external model access.
No additional binary archive is necessary while that ancestor is retained.
