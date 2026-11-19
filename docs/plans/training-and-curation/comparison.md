# Tuldok before and after the training-and-curation plan

**Before:** the tag `tuldok-before-training-and-curation` (`58226bb5`, 2026-11-19).
**After:** `feat/definition-first-projects` at the commit that adds this file. Nothing is pushed.

Between them: 7 phases, 50+ commits, 123 files, about 24,000 lines added. Every phase was specified first (`spec-t1.md` … `spec-t7.md`, each with an "As built" section), built by an agent on a branch of its own, reviewed, merged and tested again after the merge.

## Seeing them side by side

Both run against your lab project (`projects/surrogate-lab`) and your own Tuldok database:

| Version | Address |
| --- | --- |
| Before (the tag) | http://127.0.0.1:8093/ |
| After (latest) | http://127.0.0.1:8092/ |

Each asks for a sign-in code; one code works for both, since they share the same data folder. The newer version adds a few tables to the database, which the older one ignores, so neither disturbs the other.

**What your lab data shows today.** The lab's earlier runs were made before these contracts existed, so they have no training logs, model graphs, embeddings, annotation sets, sweeps or `serve` declarations. On the lab the new version therefore shows: the **Compare** tab (with kept-field outputs of three earlier pressure models side by side), **parallel coordinates** over the 150 pressure fits on Benchmarks, the two new tabs (**Sweeps**, **Compare**), and empty states that say what each new block needs. The rest is shown on the test fixtures. The screenshots of each check are listed below (git-ignored, on this machine under `build/qa/`).

## What changed, tab by tab

| Where | Before | After |
| --- | --- | --- |
| Tabs | Map, Data, Annotate, Train, Benchmarks, Analysis, Overview | adds **Sweeps** and **Compare**; the tab bar scrolls instead of widening the page; on a phone the tabs take their own row |
| Train → a run | progress, standard output and error | **live training curves** (series, several runs overlaid, smoothing, log scale, step or time), **weight and gradient histograms over steps**, a strip of **samples**; all updated in place while the run writes |
| Train → served models | — | **serve a trained model** from its own `serve.py` (`load`, `predict`), on this machine, behind Tuldok's credentials: `POST /api/serve/<model>/predict`; start, approve, stop, "Try it"; latency p50/p95/p99 and throughput; a served session can become a benchmark subject |
| Map → a model's drawer | card, runs, weights | adds **Structure**: the model's graph from `model-graph.json` (modules folded into groups, colour by parameters or by change from the starting weights or the parent, compared with another model, a node's tensors linked to Weights, **Open wide** over the page); **Serve** |
| Data → a dataset | records, files, look inside | adds **Map**: the dataset's embeddings in two dimensions, coloured by split or annotation, box and lasso select, **more like this, duplicates, outliers, leakage across splits, thin regions**; a selection becomes a dataset (`select`) or a freeze; an **Embed** form (default embedder **EmbeddingGemma 2** through Pumas) |
| Annotate | decision, class, tags, text, boxes, spans, segments; suggestions | adds **polygons, masks, depth maps, keypoints, ranking, time series, tracks, point-cloud objects, 3D boxes**; annotation **sets** made by an annotator (a project's script or a Pumas model) via the step `annotate`; **Review**: two sets side by side or overlaid, **agreement** (kappa, IoU, OKS, Kendall's τ, track switches), the most disputed records, Keep A / Keep B / both / neither, light corrections |
| Sweeps (new) | — | **hyperparameter search** on this machine: a `sweeps/<name>.json` (grid, random, halving with early stopping), one approval for the whole budget, trials as derived recipes on the Map, live state, the trials' frontier and parallel coordinates |
| Benchmarks | charts, table, compare set of 3 | adds **parallel coordinates** (metrics and varying recipe settings, brushing linked to the table and charts), **bootstrap 95 % intervals** where per-case values exist (whiskers, and frontier points marked when not told apart), a compare set of 4; opens on a benchmark with an accuracy-against-time chart |
| Compare (new) | — | 2 to 4 models: what differs, metrics with intervals, place on the frontier, and their **outputs side by side** on a shared case (native, predicted, signed error, one slice control for all) |

**For project scripts:** a small helper package, `tuldok_log`, writes these files in a few lines: `log`, `log_histograms`, `log_sample`, `autolog(model, optimizer)` for PyTorch, and `export_graph(model, example_inputs, path)`. Projects may write the files themselves instead; the formats are in `docs/contracts/project-folder.md`.

## Tests on the final code

| Suite | Before (at the tag) | After |
| --- | --- | --- |
| Project suite (`test_tuldok_project_*`) | 735 | **898**, all pass |
| Agent interface (catalog digest unchanged) | 43, 4 skipped | 43, 4 skipped |
| Workspace browser checks | 8 files | **15 files**, all pass (actions 27, annotate 11, annotation kinds 8, workspace 24, compare 6, curation 7, endpoint 8, fields 8, inside 8, serving 6, still 6, structure 8, sweeps 7, training 7, weights 7) |
| `tuldok_log` with PyTorch 2.8 on the CPU (the lab's environment, read only) | — | 13 pass |

**On your real lab data, read only:** the new reads answer on the 206-model project (map 0.09 s, compare of three models 0.04 s, parallel coordinates over 150 fits 0.05 s). One was slow and was fixed: listing servable models took 13 s and now takes 0.09 s.

## Screenshots of each new part (from the browser checks)

| Part | Directory under `build/qa/` |
| --- | --- |
| Training curves, histograms, samples, live | `project-workspace-training/` |
| Structure, folded, compared, wide | `project-workspace-structure/` (`light-1440-3c-wide.png`) |
| Compare tab, outputs, parallel coordinates, intervals | `project-workspace-compare/` |
| Annotation types, review, agreement | `project-workspace-annotation-kinds/` |
| Embedding map, curation lists, Embed form | `project-workspace-curation/` |
| Serving | `project-workspace-serving/` |
| Sweeps | `project-workspace-sweeps/` |

## Not done, and not verified

- Nothing was trained on the GPU, nothing was benchmarked, and no running Pumas was contacted. EmbeddingGemma 2, Pumas annotators and the Pumas endpoint were tested against a fake.
- Your lab has none of the new inputs yet (training logs, graphs, embeddings, annotation sets, sweeps, `serve`). A converter of the lab's earlier `history.json` into training logs was deferred.
- Known limits are in each spec's "As built". The larger ones:
  - Curation searches finish over every record only up to a few thousand records on dense data; the page says how many were examined.
  - A sweep's objectives are training metrics, not benchmark metrics.
  - Serving uses the code at HEAD, not at the product's commit.
  - Mask and depth agreement is computed pixel by pixel in Python.
  - At phone width the closed drawer still sits 9 px past the edge.
- Pumas cannot serve these models yet. It serves only models in its library, and only for fixed task types. A Pumas backend for serving is left as a seam (`serve.backend`).
