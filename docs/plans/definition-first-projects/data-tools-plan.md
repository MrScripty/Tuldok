# Plan: looking inside data, weights by layer, and generating and annotating datasets, for project folders

**Status: approved by the owner on 2026-11-13, with the changes under "The owner's answer" below.**

**Built, 2026-11-13:** phases 1 to 5, on `feat/definition-first-projects`, not pushed; the specs `spec-d1.md` to `spec-d5.md` say what was built and what was not verified, and the [ledger](execution-ledger.md) has the record. **Not built:** phase 6. **Not run:** anything against a real Pumas endpoint, which waits for the owner's word (decision 3). The owner has not yet looked at these pages.

## The owner's answer

> we will use the pumas endpoint. We wont be embedding pumas. What do you mean by lables? Right now we just need the basic modality support for data generation and annotation. text, image, audio, 3D (point clouds, mesh). We dont have a specific need for the surrogate lab. This is more a setup so other projects can setup what they need to generate. The rest sounds good. You can go ahead

What that changes in the text below, which is otherwise as proposed:

- **Pumas is an endpoint.** Tuldok calls a running Pumas gateway over HTTP and nothing else: no Pumas code is imported, bundled or started by Tuldok.
- **"Label" is replaced by "annotation":** whatever a person records about one item of a dataset. A class, tags, a caption or transcript, boxes on an image, spans in a text, timed segments in audio, or accept and reject with a note.
- **The scope is general, not the lab's.** Five kinds of record are supported from the start, each of which can be held in a dataset, looked at, annotated and imported: text, image, audio, point cloud and mesh. Arrays (the lab's fields and volumes) are a sixth kind for looking only.
- **What can be generated through the endpoint is what the endpoint declares.** Pumas 0.8.0 produces text and PNG images; its contract reserves audio output and has nothing for 3D. So text and image datasets are generated through Pumas; audio and 3D datasets come from import or from a project's own generator command, run as an ordinary build, until a served model declares that output. Tuldok offers whatever the gateway's served models declare, so nothing changes in Tuldok when Pumas gains one.
- **Decisions:** 1 as recommended (annotations are text in Git); 2 answered above; 3 and 4 as recommended.
- **The comparison of fields in the Analysis tab moves to the end** (phase 6): it serves only the lab.

## Summary

On 2026-11-13, signing the [capability check](capability-check.md) in part, the owner kept three things as requirements:

> We still want tools for generating datasets and annotating them using pumas library v0.8.0 in tuldok. Tuldok also needs to be able to look inside data. It would be great if tuldok also had a layer visulization tool so we can visualize a models weights.

Catalog mode has generation, annotation and data viewers, and keeps them. A project folder has none: its Data tab shows a card per dataset with file names and sizes, and nothing in Tuldok can open a product file. The [workspace plan](workspace-plan.md) left the record browser, the volume viewer, field slices and the Annotate tab "for a later plan". This is that plan, with a view of a model's weights added.

**The owner's rule for what goes in Git** (same day): the folder holds enough to understand the project, see how it performed and rebuild it, and no data, binaries or anything easily calculated. Applied here:

| Thing | Where | Why |
| --- | --- | --- |
| An annotation, a review decision, a note a person made | Git, as text | It cannot be calculated again |
| What to generate: model, prompts or their source, seed, count | Git, in a dataset definition | It is how the dataset is rebuilt |
| Generated images, text, audio; imported media | A product, outside Git | Data |
| A model's suggestion not yet accepted | Tuldok's database | Calculable again; becomes an annotation only when a person accepts it |
| Slices, thumbnails, histograms, layer statistics | Nowhere; computed when looked at | Easily calculated |
| The address of the Pumas gateway | The machine's settings | It differs per machine |

**The test:** on the lab folder, open a dataset, page through its samples and slice through a field; open a model and see its layers and what training changed in them. On the tiny example, annotate ten records of each kind, save, and read the annotations in `git diff`; generate a small dataset through Pumas, review it, freeze it with splits, and plan a model that trains on it.

## What exists and what is missing

| Wanted | Exists and is reused | Missing |
| --- | --- | --- |
| Look inside data | The slice inspector of catalog mode (`static/scientific-inspector.js`), the one viewer written to be mounted on another page; catalog mode's array readers, which use the standard library only | An operation that reads inside a product. The lab's data is `.npz` files of 32- and 64-bit float arrays, some inside a 9.8 GB zip, compressed. The record grid, thumbnails and stacked-slice volume exist only in the mockup |
| Weights by layer | The same array reading. Every earlier model's `weights.npz` is plain 32-bit arrays named by layer (`encoders.0.layers.0.weight`), and each run also keeps `initial-weights.npz` | The view. Nothing describes a model's architecture, so layers are grouped by name. New recipes write `model.pt`, which cannot be opened safely without PyTorch |
| Generate with Pumas | The code that discovers a gateway and calls it (`gateway_discovery`, `pumas_operations`, `image_generation`, `pumas_vision`, the request and decode functions of the proposal modules): plain functions, usable outside catalog mode | Running one as a build that makes a dataset product. Pumas 0.8.0, released today: the client for its contract is on `feat/pumas-v080-api` (three commits of 2 November, not merged here; a trial merge is clean) and predates the release |
| Annotate | The tasks and review states of catalog mode as the model; the Annotate screen of the mockup as the layout | Annotation as files. Catalog mode keeps every annotation in PostgreSQL and writes plain files only inside a frozen release |

## What has to be added to the format

1. **Records.** A dataset's product is a set of records. It says so itself with a `records.jsonl` at its root: one line per record with its id, its kind (text, image, audio, point cloud, mesh, array), its file inside the product or its text, and what is known of where it came from. A product without one is read by an optional `view` on the dataset definition (which files are records, of which kind, which array to show first), and without that every file is a record of the kind its extension says.
2. **Annotation tasks.** A new kind of definition, `annotation`: the dataset it is on, the task and its vocabulary. Tasks: accept or reject with a note, one class, tags, and a caption or transcript, on every kind of record; boxes on images; spans in text; timed segments in audio.
3. **Annotations.** `annotations/<task>.jsonl`, one line per record: the record's id and the hash of its content, the annotation, the review state (draft, reviewed, needs work, rejected), who and when, and where it came from when a model suggested it. Sorted, so a diff shows what changed. A record that no longer exists after a rebuild is reported, never dropped.
4. **Generated, imported and frozen datasets.** No new kind. A dataset's `run` names a step Tuldok itself provides: `generate` (what the table above lists), `import` (files on this machine, their kind and rights, hard-linked into a product) or `freeze` (a dataset, a task, a seed and the split shares). Both go through plan, request, approval and progress like any build, and their output is a product.

## What has to be added to Tuldok

- **Reading products.** Operations to list what a product holds (files, archive members, arrays with shape and type), to read one two-dimensional slice of an array, and to summarise an array (range, mean, spread, histogram). Each read is bounded in bytes and values; the page never receives a whole array.
- **Data tab.** A dataset opens to its records as a paged grid, and a record opens in a viewer for its kind: the text; the image; the audio with its waveform; the point cloud or mesh, turned by dragging; an array as a slice with field, axis and index and as the stacked-slice volume of the mockup.
- **A model's drawer: Weights.** Layers by name with shape and parameter count; for each, the distribution of its values and its kernels or matrix as small images; against the weights it started from and against the model it derives from, how much each layer changed.
- **Pumas.** The 0.8.0 client brought in and checked against the released contract; served models discovered from the gateway instead of typed in.
- **Annotate tab.** The mockup's screen: dataset and task, filter by state with progress, the record with its viewer, the form, keys for next and previous. With a gateway connected, "Suggest" asks a served model and shows its answer for a person to accept or change.
- **The two steps,** `generate` and `freeze`, and a Generate and a Release panel on the Data tab that write the definition for them.

## Phases

| # | Phase | Size | Done when |
| --- | --- | --- | --- |
| 1 | Reading products; the Data tab's record grid and the viewers for text, image, audio, point cloud, mesh and array | Medium | A product holding each kind is paged through and every kind is shown; on the lab folder a sample of the 9.8 GB training view opens in under two seconds |
| 2 | Weights in a model's drawer | Small | For an earlier lab model the layers, their distributions and the change from its starting weights are shown; `.npz` and `.safetensors` are read, `model.pt` says why it is not |
| 3 | The Pumas 0.8.0 client | Small | The branch is merged, its tests pass against fakes built from the released contract, and a gateway's served models are listed |
| 4 | Annotation: the format, the operations, the Annotate tab, `import` and `freeze` | Large | On the tiny example records of each kind are imported and annotated from the page, Save writes `annotations/`, a fresh clone shows the same annotations, and a frozen dataset with splits is built from them |
| 5 | `generate` through the Pumas endpoint, and suggestions in Annotate | Medium | A small text dataset and a small image dataset are generated through a fake gateway, reviewed and frozen; a suggestion is accepted and saved as an annotation that names the model |
| 6 | Native, predicted and signed error side by side in the Analysis tab, where a run kept its predictions | Small | On the lab folder one case of one earlier model is compared |

Phases 1 and 2 come first because the Annotate screen is built on the viewer, and because they serve the lab now. Each phase is specified, built by Opus 5.5 agents at medium effort and reviewed, as before. Nothing in phases 1 to 4 trains, benchmarks or uses the GPU.

## Out of scope

- A model's activations for an input, and a drawn graph of its architecture: both need the model to be run or described, which nothing records yet.
- Any change to catalog mode. Its tools stay as they are.
- Moving existing catalog annotations into a project folder.
- Video. Pumas names it as a kind of content; nothing here reads or shows it yet.

## Decisions needed

1. **Where annotations live.** As text in the Git folder, as above. Recommended: it is the one kind of data here that cannot be made again.
2. **What to generate and annotate first.** Answered by the owner: basic support for text, image, audio, point clouds and meshes, as a setup other projects build on.
3. **A real Pumas run.** The phases are built and checked against fakes. Proving phase 5 on the real gateway means one small generation by a model Pumas serves, which uses the GPU for a moment. Recommended: on the owner's word, as the tiny training runs were.
4. **Weights of new models.** Recommended: Tuldok reads `.npz` and `.safetensors` and never opens `model.pt`; the lab's training code writes one of the two beside it, when training resumes.

## Risks

- **Large products.** One dataset is a 9.8 GB zip of 783 compressed files. Listing reads the index only; a sample is decompressed alone (2 to 3 MB). Anything larger than the bound is refused with its size.
- **No numpy in Tuldok's environment.** Statistics over an array are plain Python: fast enough for a slice or a weight file of a megabyte, and sampled above a set number of values, saying so.
- **Pumas 0.8.0 moved after the client was written.** The pinned commits are in the release, but the typed contract has not been compared; phase 3 does that first.
- **Annotations and rebuilt data.** A generated dataset built again may differ. Annotations are tied to content, so those that no longer match anything are listed for the person to deal with.
