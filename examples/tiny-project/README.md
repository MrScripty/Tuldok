# Tiny project

The smallest real Tuldok project: a dataset, a network trained on a GPU, a
benchmark and two charts, and beside them a few small files of each kind
brought in, annotated and frozen with splits. Building it end to end takes about a minute, and it
uses every part of a build: environments, a command per definition, a product
passed from one definition to the next, progress lines while training, a
benchmark's results imported into the database, and charts drawn from them.
Copy it as the starting point for a project of your own.

The task: read 64 noisy samples of a sine wave whose amplitude, frequency and
phase are random, and predict the next 16 samples of the clean wave.

| Folder | Holds |
| --- | --- |
| `project/` | the project folder: `tuldok.json` and the definitions |
| `code/` | the code root (`code_root` is `../code`): the scripts the commands run |

| Definition | What it does |
| --- | --- |
| `environments/cpu` | Python 3.12 with numpy 2.3.5 |
| `environments/gpu` | Python 3.14 with torch 2.14.0+cu132 and numpy 2.5.3, with CUDA |
| `datasets/waves` | `make_waves.py` writes `waves.npz`: 4,000 training and 400 test waves from seed 7 |
| `models/small-net` | `net.py`'s `SmallNet`: fully connected, 64 to 256 to 256 to 16 |
| `recipes/small-net-a` | `train.py` trains it on the GPU for the updates in `code/settings/small-net-a.json` |
| `benchmarks/held-out` | `bench.py` scores a subject on the 400 test waves: error (RMSE) and time per wave |
| `charts/held-out-ranking` | the subjects ranked by error |
| `charts/held-out-tradeoff` | error against time per wave |
| `datasets/samples` | the step `import`: the files under `code/samples` (two texts, a PNG, a WAV, a PLY point cloud and an OBJ mesh, written by `make_samples.py`), one record each |
| `annotations/sample-quality` | a `class` task on `datasets/samples`: whether each sample is clean; its annotations are `annotations/sample-quality.jsonl` |
| `datasets/samples-v1` | the step `freeze`: the samples whose quality is accepted, split three to one from seed 7 |

The benchmark has two subjects: `small-net-a`, the trained network, and
`predict-zero`, which always predicts zero and shows the error any model has to
beat.

## What it needs

- Two Python interpreters that already exist on the machine (there is no
  `install` section, so Tuldok does not install them; it connects them):
  - one with **Python 3.12 and numpy 2.3.5** for `environments/cpu`;
  - one with **Python 3.14, torch 2.14.0+cu132 and numpy 2.5.3**, on a machine
    where torch sees a CUDA GPU, for `environments/gpu`.

  Versions are checked exactly. If yours differ, edit the two files under
  `project/environments/` to match, or the check fails and says what it found.
- A Postgres database for Tuldok's working copy, named by `TULDOK_DATABASE_URL`
  (or `--database-url` on every command).
- The example committed to Git. A build runs each command from a read-only copy
  of the commit, so uncommitted or untracked changes under `code/` are not seen:
  a changed tracked file stops the build, and a file that was never committed is
  missing from the copy. `--scratch` runs from the working tree instead and marks
  the products as scratch products.

## Build it

Run these from the Tuldok repository root. Replace the two interpreter paths
with your own; they must be absolute.

```sh
export TULDOK_DATABASE_URL=postgresql://...
P=examples/tiny-project/project

# Check the folder: expect "0 errors, 0 warnings".
.venv/bin/python -m tuldok_project check $P

# Connect the two interpreters. Each is checked at once; seconds each.
.venv/bin/python -m tuldok_project connect $P cpu /path/to/python3.12-with-numpy/bin/python
.venv/bin/python -m tuldok_project connect $P gpu /path/to/python3.14-with-torch/bin/python
.venv/bin/python -m tuldok_project environments $P

# See what would be built. Runs nothing.
.venv/bin/python -m tuldok_project plan $P --all

# Build everything: prints the plan, asks, then runs each step in turn.
.venv/bin/python -m tuldok_project build $P --all
```

The plan has five build steps after the two environments: `datasets/waves`,
`recipes/small-net-a`, then `benchmarks/held-out` once for each subject, and
`datasets/samples` and `datasets/samples-v1`, which Tuldok's own steps build
in a moment with no environment.

| Step | Time |
| --- | --- |
| `datasets/waves` | about a second on the CPU |
| `recipes/small-net-a` | 6,000 updates; well under a minute on a GPU, much of it starting CUDA. The recipe allows 6 minutes |
| `benchmarks/held-out` | a few seconds per subject, mostly starting torch |

### The samples, annotated

`datasets/samples` brings the files under `code/samples` in as records; open
it on the Data tab of the page (`python app.py --data CATALOG --project-folder
$P`) to look inside. On the Annotate tab, `annotations/sample-quality` shows
each record with its annotation; change one, press Keep and next, and Save
writes `annotations/sample-quality.jsonl`. `datasets/samples-v1` takes the
records whose annotation is accepted, as committed, and splits them; build it
again after committing a change to the annotations. To write the samples
again, run `python make_samples.py` from `code/`: the bytes are the same.

### Watch the training

While the recipe runs, in a second terminal:

```sh
.venv/bin/python -m tuldok_project runs $P
.venv/bin/python -m tuldok_project progress $P RUN --follow
```

`RUN` is the run id from `runs` or from the line `build` printed when the step
started; its first six characters are enough. `progress` shows the latest
`tuldok_progress_v1` line (stage `train`, updates done of 6,000, and the loss)
and the ends of the two logs, every two seconds until the run ends.

### Look at the results

```sh
.venv/bin/python -m tuldok_project results $P held-out
.venv/bin/python -m tuldok_project chart $P held-out-ranking --svg ranking.svg
.venv/bin/python -m tuldok_project chart $P held-out-tradeoff --svg tradeoff.svg
.venv/bin/python -m tuldok_project report $P --output report.html
.venv/bin/python -m tuldok_project save $P
```

`build` imports each subject's `results.json` into the database, so the charts
and the report work straight away. Write the SVG and HTML files somewhere
outside the project folder; `save` writes the benchmark's summary to
`project/results/held-out.csv`, the one built thing that belongs in the folder.

The trained network's median error should be far below the baseline's: on the
CPU, even 100 updates bring it to about 0.07 against 0.87 for `predict-zero`.

### Build again

A second `build $P --all` finds every step `built` and runs nothing. Change
`code/settings/small-net-a.json` (say, `"updates": 3000`) and `plan $P --all`
shows the recipe and the benchmark as out of date; commit the change and build
again to bring them up to date.

## Running the scripts by hand

The scripts take everything from their arguments and write only into
`--output`. To try them without a GPU, `train.py` and `bench.py` accept
`--device cpu`, which the definitions never pass; without it they refuse to run
when CUDA is missing. From `code/`, with an interpreter that has numpy and
torch, and an output directory outside the repository (datasets and weights are
never committed):

```sh
OUT=$(mktemp -d) && mkdir $OUT/data $OUT/train $OUT/bench-net $OUT/bench-zero
python make_waves.py --output $OUT/data --seed 7
python train.py --data $OUT/data/waves.npz --settings settings/small-net-a.json --output $OUT/train --device cpu
python bench.py --data $OUT/data/waves.npz --subject model:$OUT/train/model.pt --name small-net-a --output $OUT/bench-net --device cpu
python bench.py --data $OUT/data/waves.npz --subject zero --name predict-zero --output $OUT/bench-zero
```

On the CPU the 6,000 updates take about ten seconds. Set
`PYTHONDONTWRITEBYTECODE=1` to keep `__pycache__` out of `code/`.
