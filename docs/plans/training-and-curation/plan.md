# Plan: training views, model structure, generated annotation, curation, comparison, serving and search

**Status:** approved 2026-11-19 ("I agree"), with the four decisions as recommended. The baseline before this plan is the tag `tuldok-before-training-and-curation`. Embeddings through the Pumas endpoint default to EmbeddingGemma 2 (owner, 2026-11-19: "Set embeddinggemma 2 as the default embbedder for Pumas").

**Owner, 2026-11-19:** "Tuldok needs live training views and model structure viwer. … Tuldok also needs a strong set of annotation types … Tuldok centers on generated annotations rather than human made ones … automated/ai segmentors, polygons, depth mapping, image masks, ranking, time series, object tracking, point cloud objects (selecting points that belong to an object), some quality control tools like agreement betwene different models … We should also have serving trained models as a REST endpoint and autologging. … it would be great if it could compare selected models deeper like also showing output results next to eachother. … Tuldok should have curarion by embeddings. … Parallel coordinates sound very usful for Tuldok. Hyperparameter search could be usful … on tiny models localy. We are not going to add a model zoo now."

And on how Tuldok is built: "I actualy think Tuldoks expectation of projects being made with use created python scripts to be a strength … Tuldok solves larger architectural and the more difficult aspects of a complete end to end model/data workflow."

## The rule every phase follows

Tuldok does not grow a generator, a training framework or an annotation model of its own. Each capability is three parts:

1. **A file contract,** written in `docs/contracts/project-folder.md`: what a project's own script writes into its run's product (a metrics log, a graph, annotations, embeddings), as plain JSON, JSONL, `.npy` or PNG.
2. **A reader and a view in Tuldok:** standard library only, nothing unpickled, nothing of the project's code run inside Tuldok's server, bounded reads, as in the data tools.
3. **A thin optional helper,** `tuldok_log`, a small Python package a project's script may import to write those files in a few lines. It depends on the standard library, and on PyTorch only where it needs a model (graph export, autologging). It lives in the Tuldok repository and is installed into a project's environment like any other dependency; a project may also write the files itself.

Projects keep writing their own Python (by hand or by an AI). Tuldok supplies the contracts, the orchestration (builds, approval, runs), and the views.

## Why the structure needs the training code

The model's structure is defined, as the owner says: it is the Python class that builds the layers and its `forward` method. But that definition is code, and the files Tuldok can read today hold none of it:

- A weights file (`.npz`, `.safetensors`) is only named arrays: `encoder.0.weight` with its shape and values. It says nothing about which layer feeds which.
- `model.pt` saved with `torch.save(model)` is a pickle that names the class by its import path; loading it runs the project's code. Tuldok never opens a pickle.
- The lab's `model-definition.json` describes the model in the lab's own words (encoder widths 8, 16, 24, 32, bottleneck 48, SiLU, two convolutions a block). That is a good card, but not a graph Tuldok can draw for any project.

So the graph has to be produced where the code already runs: in the project's environment, by its training script, once, with an example input. PyTorch can do this: `torch.export` (or `torch.fx`) runs the model on an example input and records each operation, its inputs and outputs, their shapes, and the module each came from. `tuldok_log.export_graph(model, example_input)` writes that record as `model-graph.json` next to the weights. Models whose `forward` branches on data values may not export whole; the helper then writes the module tree (layers, nesting, parameters) without the data flow, and says so in the file.

## Phases

| # | Phase | Size | Done when |
| --- | --- | --- | --- |
| 1 | **Autologging and live training views.** Contract: `training/metrics.jsonl` (one line per log: step, wall time, any named scalars), `training/histograms.jsonl` (per layer, per N steps: bins of weights and gradients), `training/samples/` (an image or a field every N steps), the checkpoint index. `tuldok_log`: `log(step, **scalars)`, `log_sample(...)`, and `autolog(model, optimizer)` for PyTorch, which records loss, learning rate, gradient norm and histograms without the script naming them. Train tab: a running run's curves drawn live and updated in place, several runs overlaid, smoothing, log scale; histograms over steps per layer; the samples as a strip. A converter for the lab's earlier `history.json` is a lab script, not Tuldok code | Medium | A tiny CPU stand-in run logs through `autolog`; its curves grow on the page while it runs without the page being rebuilt; two finished runs overlay; an earlier lab run's history is shown after the lab's converter runs |
| 2 | **The model structure viewer.** Contract `model-graph.json`: nodes (operation, module path, parameter tensors, input and output shapes, attributes), edges, the module tree. `tuldok_log.export_graph`. In a model's drawer: the graph drawn left to right, modules folded into groups that open, a node's tensors linked to the Weights block; overlays coloured on the graph (parameter count, change against the parent or the starting weights, time per operation when profiled); two models' graphs side by side with matching modules lined up | Medium | A fixture model with nested modules is exported in a test environment with PyTorch and drawn; folding, the weights link and the change overlay work; two variants of one architecture are compared |
| 3 | **Comparing chosen models deeply.** The Map's compare set (two to four models) opens a Compare view: one column per model, rows of what differs (recipe settings, data, parent, kind of change), metrics with confidence intervals, where each sits on the frontier; then the outputs: one case chosen, every model's prediction in a row with the native field and each one's signed error, the same slice and axis for all, moved together. Benchmarks gains parallel coordinates (recipe settings and metrics as axes; a range dragged on an axis keeps the runs inside it) and bootstrap confidence intervals from per-case values, with frontier points marked when their difference is not significant | Medium | On the lab folder three earlier pressure models with kept fields are compared on one case; parallel coordinates over the 150 fits filters to the best errors and shows their settings |
| 4 | **Generated annotation, more kinds, and quality control.** New annotation kinds: polygons, image masks (PNG or run-length), depth maps (`.npy` per image), keypoints, ranking, time-series segments, object tracks (an object's identity across frames or time), point-cloud objects (point indices or per-point instance ids), 3D boxes. Every annotation names what made it (model, version, settings, or a person). An **annotator step**: a project's script, or a model behind the Pumas endpoint, writes annotations for a dataset; people review instead of drawing. Quality control: agreement between annotators, human or model (IoU for masks, polygons, boxes and point sets; rank correlation for rankings; agreement scores for classes), a list of the records where they disagree most, filters by confidence; two annotators shown side by side | Large | On the tiny example, two stand-in "segmentors" annotate the same images and point clouds; their masks and point objects are drawn as overlays; agreement is computed against the test's own arithmetic; the most-disputed records are listed and one is reviewed and kept |
| 5 | **Curation by embeddings.** Contract: an embeddings product (a vector per record, by record id, `.npy` plus an index), made by a project's script or by a model behind the Pumas endpoint (0.8.0 declares `embeddings_float32`). Data tab: a map of the dataset in two dimensions (projection written by the script, or a principal-component projection Tuldok computes for small sets), coloured by any field or annotation; near-duplicates; "more like this"; outliers; thin regions; near-copies across the training and validation splits (leakage). A selection becomes a dataset definition (a subset, or Freeze from it) | Medium | On a fixture with planted duplicates and one leaked validation record, both are found; a selection on the map is frozen into a dataset whose records are exactly those chosen |
| 6 | **Serving a trained model.** A recipe may declare `serve`: the project's own entry point (a script with a `predict` function). Train tab starts and stops it as a local REST endpoint behind Tuldok's credentials, loopback only, on the owner's approval like a build; each request's time is logged, so "the model as served" can be a benchmark subject | Medium | A stand-in model is served, answers a request through Tuldok's endpoint with a credential and refuses one without; its timings appear as a benchmark subject |
| 7 | **Hyperparameter search on this machine.** A `sweep` definition: the recipe it varies, parameters with ranges, a strategy (grid, random, successive halving that stops poor runs early), one or two objectives, a budget (runs, minutes, one at a time). One approval covers the whole budget. Each trial is a recipe on the Map, grouped under the sweep; two objectives give the frontier; parallel coordinates is its main view | Medium | A sweep of a tiny CPU stand-in runs within its budget, stops poor trials early, and its trials appear on the Map, the frontier and parallel coordinates |

**Order.** Phases 1 and 2 first: they are what the owner named first, and both can be checked now against existing lab runs and tiny stand-ins. Phase 3 next, because it reuses kept fields and serves the two targets directly. Then 4 and 5 (data quality), then 6 and 7.

**Compute.** Nothing in these phases trains a real model or benchmarks one. Tests use stand-in scripts that finish in seconds on the CPU. Phase 2's graph export needs PyTorch in a test environment (CPU only). Any GPU use waits for the owner's word, as before.

## Out of scope

- A model zoo. Later, perhaps, a community hub where people share models and datasets made with Tuldok.
- Distributed or cloud training.
- A built-in data-generation language; projects write scripts.
- A manual annotation editor of Label Studio's breadth: people review generated annotations and correct them, but Tuldok does not aim to be the best drawing tool.
- Video as a record kind. Object tracks work over frames stored as images, or over time in a sequence.

## Decisions needed

1. **This plan and its order.** Recommended as written.
2. **Where embeddings come from.** Recommended: both a project's script and the Pumas endpoint.
3. **The `tuldok_log` helper as a package in the Tuldok repository** that projects install. Recommended: yes, kept small; projects may ignore it and write the files themselves.
4. **Serving reachable only from this machine at first.** Recommended: yes; a remote address is a later choice.
