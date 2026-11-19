# Tuldok and the tools that do the same jobs

Researched 2026-11-18. Four areas were surveyed in parallel: annotation and dataset curation; experiment tracking, lifecycle and versioning; synthetic data generation, model visualisation and evaluation harnesses; physics-AI and simulation-surrogate platforms. Web facts were read on 2026-11-18 unless dated otherwise. Open-source repositories were cloned shallowly and read, never built or run, under `workspace/scratch/competitor-repos/` (about 3.9 GB in all: label-studio, cvat, argilla, doccano, mlflow, clearml, dvc, aim, zenml, distilabel, netron, WeightWatcher, BlenderProc, model-explorer, lm-evaluation-harness, physicsnemo, neuraloperator, PDEBench, the_well, deepxde). FiftyOne (2.1 GB) was grepped and deleted; Rerun was read through the GitHub tree.

**[unverified]** marks a claim taken from vendor marketing, an aggregator or memory and not confirmed in a primary source. Tuldok's column describes the branch `feat/definition-first-projects` as of today (project-folder mode, the Map workspace, data tools phases 1 to 6) plus catalog mode.

## 1. The short answer

**Nobody else does the whole loop.** Tuldok's purpose is: make or import data, look inside it, annotate it, freeze it, define models and how they are trained, build them, benchmark them, and see the results. That spans what is usually four products:

| Job | Usual tools | Tuldok |
| --- | --- | --- |
| Annotate and curate | Label Studio, CVAT, FiftyOne, Encord, Labelbox | Annotate tab, Look inside, Freeze |
| Track, version, reproduce | MLflow, W&B, ClearML, DVC, ZenML | Git folder of definitions, Map, Train, builds |
| Generate data, inspect models, evaluate | distilabel, Replicator, Netron, TensorBoard, lm-eval | Generate via Pumas, Weights, Benchmarks |
| Physics surrogates | PhysicsNeMo, NeuralOperator, SimAI, PhysicsX, Simcenter | Benchmarks, Analysis (kept fields), project's own solver step |

**Three things only Tuldok has**, confirmed by searching the code of the open tools and the documentation of the closed ones:

1. **An accuracy-against-time chart with the Pareto frontier.** No tracker draws one (MLflow, ClearML, DVC, ZenML, Aim: the word "pareto" appears in MLflow only inside its GEPA prompt optimiser, and in ClearML's SDK only where `HyperParameterOptimizer` sorts multi-objective trials by successive Pareto fronts, a ranking with no chart; see section 5a), no harness (lm-eval, HELM, Inspect, Promptfoo, MLPerf) and no physics benchmark (PDEBench, The Well, PhysicsNeMo-CFD) draws one. MLPerf sets an accuracy pass mark and then ranks by speed; HELM and Promptfoo add speed as a column; W&B can be made to draw one with a custom Vega panel. For a project with two targets, accuracy-first models and real-time models, this is the central view, and it is Tuldok's.
2. **A family tree of models.** Others draw how files were produced: W&B artifact lineage, ClearML parent tasks, ZenML pipeline DAGs, DVC `dvc dag`, Valohai data heritage, Ansys SimAI's 2026 R1 Build panel. None shows which model derives from which with the kind of change, groups and comparisons, as the Map does. The nearest real model tree is the Hugging Face Hub's `base_model` tree, outside these tools.
3. **A project that is a Git folder of definitions only,** with the working copy in a database, weights and products kept out of Git on the machine, and no hash lockfiles. Only DVC (`dvc.yaml`, plots declared in files, experiments as Git refs) and Valohai (`valohai.yaml`) keep definitions in Git, and DVC rests on hash lockfiles. Charts declared as files: Tuldok and DVC only.

**Also rare:** agents may ask for a build and only the owner approves it (Valohai's `require-approval` nodes and ZenML's Slack ask-steps come close; no tool has a queue of agent requests); annotations stored as text in Git (CVAT removed its Git sync; Hugging Face datasets are Git repositories but have no annotation); one viewer for text, image, audio, point clouds, meshes and arrays (FiftyOne has no audio; Label Studio Community has no 3D; Rerun views but does not annotate); weights compared with the weights a model started from or with its parent (WeightWatcher compares base and fine-tuned models; nobody else links it to an ancestry).

**Where Tuldok trails,** in the order that matters for its stated purpose:

1. **Physics-specific learning:** no model zoo or pretrained physics models (PhysicsNeMo, NeuralOperator, The Well checkpoints), no mesh/CAD-native geometric learning, no physics-informed losses, no confidence or out-of-range flag per prediction (SimAI, physicsAI and Rescale all sell this).
2. **Scale:** no multi-GPU, cluster or cloud training; no hyperparameter search.
3. **Live training views:** no live loss curves, no weight histograms over training, no parallel-coordinates plot (nearly every tracker has one).
4. **Annotation breadth:** no polygons, masks, keypoints, cuboids or tracking; no video; no QA by consensus or ground truth; no curation by embeddings or similarity; no rank or rate questions; no standard export formats (COCO, YOLO, KITTI): Tuldok writes JSON and JSONL.
5. **Model structure:** no drawn architecture graph (Netron, Model Explorer, TensorBoard), no activations or attribution (Captum).
6. **Generation breadth:** Pumas 0.8.0 makes text and PNG images only; nothing renders 3D scenes with ground truth (Replicator, BlenderProc, Kubric), and generated data gets no real-against-synthetic quality report (SDV, MOSTLY AI).
7. **Ecosystem:** no hosted option, no large community, no ready task catalogues.

**The market is unstable,** which favours Tuldok's choice of plain definition files that do not depend on one vendor:

- Neptune shut down in March 2026 and deleted user data with no export.
- lakeFS bought DVC (2025-11) and moved lakeFS itself to BSL 1.1 (2026-09-22); DVC stays Apache-2.0.
- ClearML's server is SSPL, W&B self-hosting needs a licence, and SDV is BSL.
- Argilla is in maintenance only, HELM entered maintenance mode on 2026-06-01, Unity Perception is discontinued, and NeMo Microservices shut down on 2026-10-01.
- Gretel went to NVIDIA, Monolith to CoreWeave, Altair to Siemens, Promptfoo to OpenAI (announced 2026-03-09), and W&B is CoreWeave's.
- Determined, Pachyderm and Guild AI look dormant, and Aim's main branch has had no commits since 2025-12-31.

## 2. Area by area

### 2.1 Annotation, curation and looking at data

| Tool | Licence, price | Closest overlap with Tuldok | Better than Tuldok | Tuldok has, it lacks |
| --- | --- | --- | --- | --- |
| **Label Studio** 1.23 | Apache-2.0 open core; Starter Cloud and Enterprise by quote | Its ML backend: an HTTP server with `/predict`, `/setup`, `/train`, `/health`, predictions stored with a `model_version` for a person to accept (`label_studio/ml/api_connector.py`). The nearest thing to Pumas suggestions | About 20 control tags (polygon, brush, keypoint, relations, ranker, pairwise, time series, video tracking, PDF); about 10 export formats | 3D in the open edition (LiDAR is Enterprise), meshes, arrays, annotations in Git, frozen releases, training and benchmarks |
| **CVAT** 2.83 | MIT; cloud from $23/user/month yearly | 3D point clouds with cuboids, audio (new in 2026), and a pull-based CLI agent that runs your own model | The 2D/3D vision editor, tracking with interpolation, quality control and consensus, about 30 export formats | Meshes, arrays, text; Git sync was removed (`cvat/apps/dataset_repo/README.md`); no releases; no training |
| **FiftyOne** 1.22 | Apache-2.0 open core; enterprise "Voxel51" by quote | Meshes (glTF, OBJ, PLY, STL), point clouds, Gaussian splats, MCAP/ROS/Rerun import | Curation: views, embeddings, similarity, evaluation panels, large model zoo | Audio; annotations in Git; versioning (Enterprise only: read-only snapshots) |
| **Rerun** 0.43 | Apache/MIT; Hub priced per deployment | Viewing `volume_3d`, `voxel_grid_map`, `tensor`, `mesh3d`, audio | Large time-indexed 3D and volume viewing; a reference design for solver fields | Any annotation |
| **Argilla** 2.8 | Apache-2.0, maintenance only | Suggestions with the model that made them | Rank and rate questions, vector search | 3D, audio, being maintained |
| **Doccano** 1.8 | MIT | Auto-labelling through any REST endpoint, with a response mapping | Sequence labelling, intent and slot | 3D, releases, training |
| **Prodigy** | Proprietary; $390 personal, $490 per seat | Local, scriptable, model-in-the-loop accept or reject | The fastest accept/reject flow; any API from a recipe | 3D, frozen releases, open source |
| **Hugging Face Hub** | Hosted; viewer on private data needs a paid plan | Every dataset is a Git repository | Distribution at scale, SQL console | 3D viewer, annotation |
| **Encord, Labelbox, V7, Supervisely, SuperAnnotate, Scale Nucleus, Roboflow** | Closed, mostly by quote | Encord: LiDAR to 10M points a frame, DICOM; Supervisely: the widest modality range, meshes by export apps | Team workflows, QA, active learning, hosted models | Local-first, open, Git text, links to training and benchmarks |

### 2.2 Tracking, lifecycle, versioning

| Tool | Licence, price | Core model | Better than Tuldok | Tuldok has, it lacks |
| --- | --- | --- | --- | --- |
| **MLflow** 3.18 | Apache-2.0 | Logged runs in SQLite by default; registry; GenAI tracing | Autologging, scale, serving; a built-in MCP server and an in-app assistant (`mlflow/mcp/server.py`, `mlflow/assistant/`); parallel coordinates and scatter | Definitions in Git, model tree, Pareto chart, approval, annotation, weights |
| **W&B** | SDK MIT, server proprietary; self-hosting licensed | Logged runs; Artifacts lineage DAG | Polish, Sweeps, Reports, collaboration; official MCP server | Free local use beyond personal, definitions in Git, approval |
| **ClearML** 2.2 | SDK Apache-2.0, server SSPL | Auto-captured runs; clone, edit, re-enqueue | Remote execution on queues, comparisons, HPO | Open server licence, Git definitions, model tree |
| **DVC** | Apache-2.0 (now owned by lakeFS) | `dvc.yaml` stages in Git, plots in files, `dvc repro` | Content-addressed remote for large files, experiments as Git refs | GUI (only Studio), roles, MCP, model semantics; Tuldok avoids its hash lockfiles |
| **ZenML** 0.98 | Apache-2.0; Pro paid | Code-defined pipelines, model control plane | Orchestration across stacks; official MCP server; ask-steps for approval | Git definitions, model tree, Pareto |
| **Valohai** | Commercial | `valohai.yaml` in Git, immutable outputs | `require-approval` pipeline nodes, managed compute | Open source, local |
| **Aim, TensorBoard, Trackio** | Apache-2.0 / Apache-2.0 / MIT | Local logged metrics | Live curves, histograms, HParams, projector (TensorBoard); W&B-compatible logging (Trackio) | Definitions, lineage, roles |
| **Kubeflow, Metaflow, Polyaxon, Determined, Pachyderm** | Apache-2.0 | Cluster pipelines | Distributed training, HPO | Local simplicity; two are dormant |
| **Neptune** | Shut down March 2026 | | | A warning about SaaS-only tracking |

### 2.3 Generation, model inspection, evaluation

| Tool | What it is | Better than Tuldok | Tuldok has, it lacks |
| --- | --- | --- | --- |
| **distilabel** (Apache-2.0; last commit 2025-12-15) | LLM pipelines for synthetic text: Self-Instruct, Evol-Instruct, Magpie, UltraFeedback, judges; any OpenAI-compatible `base_url`; Ray | Recipes and judges, many providers, scale-out | Review built in, frozen releases, non-text data |
| **NeMo Data Designer** (ex-Gretel, Apache-2.0) | Column-by-column datasets from samplers and LLMs, with validators | Declarative schema with validators | Review, freeze, training |
| **Omniverse Replicator / Cosmos** (NVIDIA licences) | Randomised USD scenes rendered with ground truth (boxes, segmentation, depth, point clouds) | Physically based rendering and sensor simulation | Openness, review, freeze |
| **BlenderProc** (GPL-3), **Kubric** (Apache-2.0) | Blender rendering pipelines with depth, segmentation, flow; Kubric adds PyBullet physics | 3D scenes with ground truth, video | Both could run as a Tuldok project's own command |
| **SDV** (BSL), **MOSTLY AI** (Apache-2.0 SDK) | Tabular generators with quality reports | Real-against-synthetic fidelity scores | Tuldok has no tabular generation |
| **Netron** (MIT) | Graph viewer for about 180 formats; opens `.pt` pickles with a JavaScript unpickler that runs no Python (`source/python.js`) | Architecture graph; safe reading of nearly every format | Distributions, kernels as tiles, change against parent or start, links to runs and benchmarks |
| **Model Explorer** (Apache-2.0) | GPU-drawn graphs, side-by-side graphs, per-node data overlays from JSON | Overlays and graph comparison | It loads `.pt2` with `torch.export.load`, trusting the file |
| **WeightWatcher** (Apache-2.0) | Per-layer spectral quality (alpha) without test data; base vs fine-tuned | Data-free layer quality | Ancestry, GUI; it loads `.bin` with `torch.load` and relies on torch's `weights_only` default |
| **TensorBoard** | Scalars, histograms over steps, graph, projector | Training-time views | Definitions, ancestry |
| **lm-eval, HELM, OpenCompass, Inspect, Promptfoo, MLPerf** | Language-model evaluation; MLPerf for systems | Task catalogues, standard errors, per-sample transcripts, sandboxes | Any non-language metric, the Pareto chart, ancestry |

Tuldok never opens a pickle: `.pt` files are listed with the reason (spec-d2, decision 4). Netron's approach, a pickle reader that runs no code, is the one to copy if `.pt` files must be read.

### 2.4 Physics AI and surrogates

The field has four layers. Tuldok sits in a fourth that only closed enterprise products occupy, and they aim at a different buyer.

1. **Libraries you fork:**
   - **PhysicsNeMo** 2.2 (Apache-2.0; Hydra configs; FNO, MeshGraphNet, Transolver, DoMINO; multi-GPU and domain-parallel; CFD metrics including force coefficients and spectra). Its `benchmarks/` folder times library code, not models.
   - **NeuralOperator** 2.0 (MIT; FNO, TFNO, UNO, SFNO, GINO and more).
   - **DeepXDE** (LGPL-2.1; physics-informed networks).
   - None has a project, a model tree, an accuracy-against-time view or a GUI.
2. **Benchmark datasets:**
   - **PDEBench** (MIT, but `pdebench/models/metrics.py` carries an NEC non-commercial header: do not copy it).
   - **The Well** (BSD-3; 15 TB across 16+ datasets; the best-specified HDF5 format; a ready true / predicted / |error| video per field).
   - Both report accuracy only.
3. **Solvers that make data:** PhiFlow, JAX-Fluids, Warp and Newton, Genesis World 1.x, Taichi. Each could be a Tuldok project's own solver step.
4. **Commercial surrogate platforms, the real competitors:**

   | Platform | What it offers | Notes |
   | --- | --- | --- |
   | Ansys SimAI (now Synopsys) | Full 3D fields from 30–100 earlier simulations, with confidence for out-of-range designs | An automatic evaluation report; a Build panel in 2026 R1; a desktop Pro tier |
   | Siemens Simcenter ROM, HEEDS AI and the former Altair physicsAI / romAI | Geometric learning on native meshes, flags for out-of-range designs | FMU export for real-time system simulation |
   | PhysicsX | Data Factory, large geometry models, applications | Raised $300M in June 2026 [unverified] |
   | Neural Concept | CAD-native design copilot | Raised $100M in December 2025 |
   | Rescale AI Physics | Cloud HPC solvers with a dataset-creation agent, Auto Tune and confidence estimates | |
   | Monolith (CoreWeave) | Engineering test data | |
   | Luminary Cloud | Cloud CFD with a surrogate | |

   All are closed and priced by quote.

**Nobody targets games.** The nearest things are FMU reduced-order models for real-time system simulation (Siemens, Altair), NVIDIA's Omniverse digital-twin blueprint (a live surrogate in a rendered scene, not a game export), and Taichi's AOT runtime. A benchmark subject that is the model *as deployed* (timed on ONNX Runtime or inside an engine) would be a feature nobody in the field has.

**How kept fields compare** (phase 6): The Well's true / predicted / |error| rows and PhysicsNeMo's `pred_`/`true_` mesh fields are offline files for ParaView or a video. SimAI and Simcenter show predicted fields in 3D viewers (side-by-side error views [unverified]). Tuldok's Analysis tab shows native, predicted and *signed* error side by side, with whole-field figures, in the same place as the benchmark that scored the model.

## 3. Feature matrix

✓ yes · ~ partly or in a paid tier only · ✗ no · ? unverified. One column per family where the members agree; the area sections above have the detail.

| Capability | Tuldok | Label Studio | CVAT | FiftyOne | MLflow | W&B | ClearML | DVC | ZenML | TensorBoard | Netron | PhysicsNeMo | The Well / PDEBench | SimAI / Simcenter / PhysicsX |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Fully open source | ✓ | ~ open core | ✓ | ~ open core | ✓ | ✗ | ~ SSPL server | ✓ | ~ | ✓ | ✓ | ✓ | ✓ | ✗ |
| Local-first, no account | ✓ | ✓ | ✓ | ✓ | ✓ | ~ personal | ~ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ~ desktop tier |
| Project = definitions in Git | ✓ | ✗ | ✗ | ✗ | ~ | ✗ | ✗ | ✓ | ~ | ✗ | – | ~ configs | ~ configs | ✗ |
| Weights kept out of Git | ✓ | – | – | – | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | ✓ | ✓ | ✓ |
| Text / image / audio data | ✓ | ✓ | ~ no text | ~ no audio | – | ~ | ~ | – | – | ~ | – | ✗ | ✗ | ✗ |
| Point cloud / mesh / arrays | ✓ | ~ Ent LiDAR | ~ PCD only | ✓ | – | ✗ | ✗ | – | – | ✗ | – | ✓ (in code) | ✓ arrays | ✓ meshes |
| Video | ✗ | ✓ | ✓ | ✓ | – | ~ | ~ | – | – | ✗ | – | ✗ | ✗ | ? |
| Annotation, shapes beyond boxes | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Annotations as Git text | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ~ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Model suggestions, human accepts | ✓ Pumas | ✓ ML backend | ✓ Nuclio, agent | ~ in-process | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Frozen release with provenance | ✓ | ~ snapshots | ✗ | ~ Ent | ~ | ✓ Artifacts | ✓ Datasets | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ fixed sets | ? |
| Curation by embeddings | ✗ | ✗ | ✗ | ✓ | ✗ | ~ | ~ | ✗ | ✗ | ~ projector | ✗ | ✗ | ✗ | ✗ |
| Standard export formats | ✗ JSON/JSONL | ✓ | ✓ ~30 | ✓ | – | – | – | – | – | – | – | ✓ HDF5/Zarr | ✓ HDF5 | ? |
| Data generation step | ✓ Pumas text/PNG; own command | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ stages | ✓ steps | ✗ | ✗ | ✗ | ✓ PDEBench scripts | ~ |
| Training regime as definition | ✓ recipes | ✗ | ✗ | ✗ | ~ MLproject | ~ | ~ | ✓ | ✓ | ✗ | ✗ | ✓ Hydra | ✓ Hydra | ~ automatic |
| Rebuild from definitions | ✓ | ✗ | ✗ | ✗ | ~ | ~ | ~ | ✓ | ~ | ✗ | ✗ | ~ | ~ | ✗ |
| Live training curves | ~ progress | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ | ~ | ~ | ✓ | ✗ | ✓ TB | ✓ | ? |
| Hyperparameter search | ✗ | ✗ | ✗ | ✗ | ~ | ✓ | ✓ | ✗ | ~ | ✗ | ✗ | ~ | ✗ | ✓ automatic |
| Multi-GPU / cluster / cloud | ✗ | – | – | – | ✗ | ~ | ✓ | ✗ | ✓ | – | – | ✓ | ~ | ✓ |
| Model family tree | ✓ Map | ✗ | ✗ | ✗ | ✗ | ~ artifact DAG | ~ parents | ~ dag | ~ DAG | ✗ | ✗ | ✗ | ✗ | ~ Build panel |
| Benchmarks as definitions | ✓ | ✗ | ✗ | ~ | ✗ | ✗ | ✗ | ~ metrics | ✗ | ✗ | ✗ | ~ | ✓ | ✗ |
| Accuracy-vs-time Pareto chart | ✓ | ✗ | ✗ | ✗ | ✗ | ~ custom Vega | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Parallel coordinates | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ | ~ | ✗ | ✓ | ✗ | ✗ | ✗ | ? |
| Charts declared as files | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Per-case values | ✓ | – | – | ✓ | ~ | ~ | ~ | ✗ | ✗ | ✗ | ✗ | ✓ metrics.jsonl | ~ | ? |
| Native / predicted / error fields | ✓ Analysis | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ~ files | ~ video | ✓ 3D viewer |
| Confidence per prediction | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ~ UQ | ✗ | ✓ |
| Weights: layers, distributions | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ histograms | ✗ | ✗ | ✗ | ✓ | ~ stats | ✗ | ✗ | ✗ |
| Weights: change vs parent / start | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Architecture graph | ✗ | ✗ | ✗ | ✗ | ✗ | ~ | ✗ | ✗ | ✗ | ✓ | ✓ | ✗ | ✗ | ✗ |
| Pretrained models / zoo | ✗ | ✗ | ~ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | – | ✓ | ✓ | ✓ |
| Agents request, owner approves | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ~ ask step | ✗ | ✗ | ✗ | ✗ | ✗ |
| MCP server | ✓ with grants | ~ | ~ | ? | ✓ | ✓ | ~ community | ✗ | ✓ | ✗ | ✗ | ~ skill | ✗ | ~ SDK |
| Roles | ✓ owner/edit/inspect | ~ Ent | ✓ | ~ Ent | ✓ | ✓ | ~ paid | ~ Studio | ~ Pro | ✗ | ✗ | ✗ | ✗ | ✓ |
| Hosted option, large community | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Real-time / game deployment | ✗ (a stated goal) | – | – | – | ~ serving | ✗ | ~ | ✗ | ~ | – | – | ~ Omniverse twin | ✗ | ~ FMU ROMs |

## 4. What to do with this

### Defend (what nobody else has, and what serves both targets)

1. The tradeoff chart and frontier. Add an MLPerf-style preset: "accuracy at least X, then fastest", and allow a benchmark subject to be the model *as deployed* (ONNX Runtime, a game engine) so the real-time target is measured where it runs.
2. The Map. Keep derivations, kinds of change and comparisons first-class; nobody else has them.
3. Definition-only Git folders with no hash lockfiles, and charts as files.
4. Owner approval of agent requests. MLflow, W&B and ZenML now have MCP servers, but none has grants or an approval queue.

### Borrow (ideas and formats, not code, unless the licence allows)

| Idea | From | Size |
| --- | --- | --- |
| Import The Well and PDEBench HDF5; PhysicsNeMo `metrics.jsonl` as per-case values and `pred_`/`true_` fields as kept fields | The Well, PDEBench, PhysicsNeMo | Small to medium |
| Spectral (Fourier-band) error, rollout errors over time, integrated quantities (forces) as benchmark metrics | PDEBench, The Well, PhysicsNeMo-CFD | Small |
| A confidence / out-of-range flag per prediction | SimAI, physicsAI, Rescale | Medium (needs the training code's help) |
| Parallel coordinates on Benchmarks | MLflow, W&B, TensorBoard | Small |
| Live training curves on Train from a run's progress | every tracker | Small |
| Weight distributions across checkpoints in training order | TensorBoard, W&B | Small (the lab keeps checkpoints) |
| An architecture graph from a recipe's model definition | Netron, Model Explorer | Medium |
| A per-layer spectral quality column | WeightWatcher (Apache-2.0) | Small |
| A pickle reader that runs no code, if `.pt` must be read | Netron (MIT) | Medium |
| Polygons, keypoints, masks; COCO / YOLO / KITTI export | Label Studio, CVAT | Medium each |
| Rank and rate annotation questions | Argilla, Label Studio | Small |
| Similarity and embedding views for curation | FiftyOne | Medium |
| A real-against-synthetic quality report for generated datasets | SDV, MOSTLY AI | Medium |
| Generation templates (Magpie, Evol-Instruct, judges) for `generate` | distilabel | Small |
| A read-only MCP mode | W&B | Small |

### Call rather than rebuild (complements)

PhysicsNeMo and NeuralOperator models as a recipe's training code; PhiFlow, Warp, Genesis or JAX-Fluids as a project's solver step; BlenderProc or Kubric as a scene generator command; Label Studio or CVAT as an external annotator for shapes Tuldok does not draw, with their exports imported.

### Licence cautions

- **Do not copy:** PDEBench's `pdebench/models/metrics.py` (NEC non-commercial header).
- **Copyleft:** DeepXDE is LGPL-2.1 and BlenderProc is GPL-3.
- **Source-available, not open source:** SDV is BSL, lakeFS is BSL from 2026-09-22, and the ClearML server is SSPL.
- **Fine with attribution:** PhysicsNeMo, NeuralOperator, The Well, Netron, WeightWatcher, Label Studio's open edition, CVAT, FiftyOne's open edition and MLflow are permissive.

## 5a. Checked by hand in the clones

The four areas were researched by separate agents. The claims this document leans on were then checked again directly in the cloned code on 2026-11-18:

| Claim | Where | Result |
| --- | --- | --- |
| CVAT removed its Git sync | `cvat/apps/dataset_repo/README.md` | Confirmed: "…synchronizing CVAT tasks with Git repositories, which was removed." |
| No tracker draws an accuracy-vs-time Pareto chart | whole-word `pareto` in mlflow, clearml, dvc, aim, zenml | **Corrected.** Earlier wording said a search finds nothing. MLflow: only `genai/optimize/optimizers/gepa_optimizer.py`, `genai/judges/optimizers/gepa.py` and their protos and docs (prompt optimisation). ClearML: `automation/optimization.py:1207`, trials sorted by Pareto fronts. DVC, Aim, ZenML: none. No chart in any of them; a case-insensitive search also matches `compareTo…` names, which explains the agent's false positives |
| Label Studio Community has no point clouds | `web/libs/editor/src`, for `lidar`, `pointcloud`, `.pcd` | Confirmed: no file |
| PDEBench's metrics file is not MIT | `pdebench/models/metrics.py`, header | Confirmed: NEC Laboratories Europe copyright header, "All rights reserved" |
| Netron reads pickles with its own reader | `netron/source/python.js:3895` | Confirmed: `registerType('pickle.Unpickler', …)` in JavaScript |
| Argilla adds no new features | `argilla/README.md` | Confirmed: "we won't be adding new features going forward" |
| MLflow has a built-in MCP server | `mlflow/mcp/server.py` | Confirmed |
| The Well renders true / predicted / error videos | `the_well/benchmark/metrics/plottable_data.py:227` | Confirmed: `make_video` |
| PhysicsNeMo's `benchmarks/` times library code | `physicsnemo/benchmarks/` | Confirmed: an ASV-style suite (`run_benchmarks.sh`), no model accuracy |

Claims about closed products, prices and 2026 company events were not checked again beyond the sources each area cites. They are listed below where they could not be confirmed.

## 5. Not verified

- **Commercial physics platforms:** most capability claims are marketing, especially whether they show error fields and whether they track lineage.
- **Prices and plans:** Labelbox, V7, Roboflow Core, Voxel51 Enterprise and the W&B tiers.
- **Capabilities:** Labelbox and V7 LiDAR support; whether FiftyOne has an MCP server; JAX-Fluids' licence; Taichi's current activity.
- **Recent events:** PhysicsX's 2026 round, the Anaconda–Outerbounds deal, and the date Warp's licence changed.
