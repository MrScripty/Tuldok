# Implementation spec: curation by embeddings

This is phase 5 of [the training and curation plan](plan.md). It follows that plan's rule: a file contract, a reader and a view in Tuldok, and no embedder of Tuldok's own. The readers follow [spec-d1.md](../definition-first-projects/spec-d1.md) and [spec-d6.md](../definition-first-projects/spec-d6.md): standard library only, nothing unpickled, nothing of the project's code run, nothing written, bounded reads, a damaged file refused and not a failure, reads outside the service lock. The step follows [spec-d4.md](../definition-first-projects/spec-d4.md) section 6 and [spec-d5.md](../definition-first-projects/spec-d5.md) section 3 (`generate`): Pumas is reached only through `tuldok_project/pumas.py` and the 0.8.0 client of [spec-d3.md](../definition-first-projects/spec-d3.md). The page follows [spec-w4.md](../definition-first-projects/spec-w4.md): nothing is rebuilt by a timer or a return to the window.

**Owner, 2026-11-19:** "Tuldok should have curarion by embeddings. Tuldok needs to have great curaiton tools for datasets in order to build high quality training data." And: "Set embeddinggemma 2 as the default embbedder for Pumas."

**After this phase** a dataset that has embeddings opens on the Data tab as a map: its records as points in two dimensions, coloured by split, kind, an annotation the records carry or any field of theirs; beside it the near-duplicates, the outliers, the thin parts of the map, the near-copies between the training split and the others (leakage), and, for the record opened, the records most like it. A region chosen on the map becomes a new dataset of exactly those records, or opens Freeze with them. Embeddings are made by a project's own script, or by a new step `embed` that asks a model the Pumas endpoint serves, EmbeddingGemma 2 unless the definition or the machine names another. Tuldok never computes an embedding.

## 1. The file: an embeddings product

A product holds a set of embeddings `<name>` (1 to 64 characters of `a-z 0-9 . _ -`, starting with a letter or digit) as two files under `embeddings/` at its top:

- **`embeddings/<name>.npy`:** one row per record, shape `(rows, dimensions)`, `float32` (little- or big-endian; `float16` and `float64` are read too), C order, every value finite, no row all zeros.
- **`embeddings/<name>.json`,** the index, UTF-8 JSON of at most 16 MiB:

```json
{"format": "tuldok_embeddings_v1",
 "records": ["a1", "a2", "a3"],
 "dimensions": 256,
 "metric": "cosine",
 "model": {"name": "embeddinggemma-2", "model_id": "unsloth/embeddinggemma-2-GGUF", "profile": "embed-gpu",
           "capability": "text_embedding", "via": "pumas"},
 "prefix": "task: clustering | query: ",
 "source": {"dataset": "datasets/photos", "run": "4f1c…"},
 "projection": {"file": "photos.map.npy", "method": "umap"},
 "notes": ["2 point clouds were not embedded: no model the endpoint serves takes them."]}
```

- `records`: the record ids in row order, 1 to 50,000 different ids of 1 to 600 characters without control characters (a product read from its files names its records by their addresses, spec-d1).
- `dimensions`: 1 to 4,096, the second axis of the `.npy`. `metric`: `cosine` (the only one).
- `model`: an object with `name` (1 to 256 characters) and any other short facts (strings, numbers, booleans or null), shown as given.
- `prefix`: the text put before each record's text, or null. EmbeddingGemma expects a task prefix (Pumas: "task prefixes … are part of the caller's text").
- `source`: which records the rows are: `dataset` (a reference, or null for the product's own records) and `run` (the run whose product holds them, or null when the script cannot know it; section 3 finds it).
- `projection` (optional): a two-dimensional map the script made (UMAP, t-SNE, anything), a `.npy` of shape `(rows, 2)` beside the index, and its `method` (1 to 64 characters). Tuldok draws it instead of its own.
- `notes` (optional): at most 64 sentences of at most 1,000 characters.

Other keys are kept and ignored. Bounds: rows × dimensions at most 40,000,000 values (160 MB of `float32`); at most 64 sets in one product. A set breaking a rule is listed with the reason and refused `unsupported` when read; a `.npy` over the bound `too-large`.

**Who writes it.** A project's own script, in the product of a dataset (its own records' embeddings, `source.dataset` null) or of a dataset whose run takes the records' dataset as an input (`source.dataset` names it). Or the step `embed` (section 5). The contract goes into `docs/contracts/project-folder.md`.

## 2. The default embedder

When nothing names an embedding model, Tuldok uses **EmbeddingGemma 2**: the served (model, profile) whose alias or `model_id` contains `embeddinggemma-2`, ignoring case, preferring the `model_id` `unsloth/embeddinggemma-2-GGUF`, then the endpoint's order, among those with an embedding capability available. When none is served the call is refused `not-found`, naming what the endpoint serves with an embedding capability; another model is never chosen silently.

The machine's settings file (beside `pumas_endpoint`, `local.py`) may hold `embedding_model` (an alias, and optionally `embedding_profile`) to use instead of EmbeddingGemma 2, and `embedding_prefix` (default `task: clustering | query: `). A step's own `model` and `prefix` come first. The order is: the definition, the machine's setting, EmbeddingGemma 2.

- **`endpoint`** answers, besides what it did, `embedder`: `{model, profile, prefix, named_by` (`setting` or `default`)`, chosen` (the served entry it resolves to now, or null)`, problem` (why none, or null)`, embedders` (every served (model, profile) with an embedding capability available: `model`, `profile`, `model_id`, `capabilities`, `dimensions` (the advertised bound or null)`)}`.
- **`set_embedder`** (owner, changes): `model` (an alias, or null for EmbeddingGemma 2), `profile`, `prefix` (null for the default prefix). A model that the endpoint does not serve with an embedding capability is refused; the prefix is at most 1,000 characters. Answers `endpoint`'s `embedder`.

## 3. Finding a dataset's embeddings

**`embeddings`** (inspect), argument `dataset` (a reference). The dataset's current products, and the current products of every dataset whose `run.inputs` names it, are looked through for `embeddings/*.json`. A set belongs to the dataset when its `source.dataset` names it, or when it lies in the dataset's own product with `source.dataset` null. Its **records run** is `source.run` when given; else the run holding it when the records are its own; else the run the holding run recorded for that input. The answer: `dataset`, `run` (its first current product's run, or null), and `sets`, each `run` (holding it), `holder` (the dataset holding it), `name`, `rows`, `dimensions`, `model`, `prefix`, `source`, `records_run`, `current` (the records run is a current product of the dataset), `projection` (its method or null), `notes`, `problem` (null, or why it cannot be read).

## 4. Reads

Five reads, `inspect`, in `INSIDE_READS` like the others, in the `project_folder` profile and absent from `catalog` (whose digest is unchanged). Each takes `run` (holding the set), `name`, and `records_run` (whose records the rows are; default `run`), which joins the product arguments the service finds under its lock.

| Operation | Arguments | Result |
| --- | --- | --- |
| `embedding_map` | `colour` (`split`, `kind`, `annotation:<task>`, `field:<key>`; optional), `cells` (8 to 64, default 24), `thin` (0 to 1, default 0.25) | `name`, `rows`, `dimensions`, `model`, `method` (`pca`, or the script's), `explained` (the share of the variance on each axis, for `pca`), `sample` (rows the components were computed from), `ids`, `x_f32`, `y_f32` (base64), `bounds`, `missing` (rows whose record is not in the records product), `colours` (what can be chosen: `split`, `kind`, `annotation:<task>` for each task the records carry, `field:<key>` for each key of `meta` found), `colour` (`by`, `type` `category` or `number`, `categories` with counts, `codes_u16` or `values_f32` (base64, per row), or null), `grid` (`cells`, `counts` row by row), `thin` (cells) |
| `embedding_neighbours` | `record`, `limit` (1 to 200, default 12) | `record`, `neighbours` (`id`, `cosine`, `split`, `kind`), most alike first; exact |
| `embedding_duplicates` | `threshold` (0.5 to 1, default 0.98), `limit` (1 to 1,000, default 200) | `threshold`, `pairs` (`a`, `b`, `cosine`, `a_split`, `b_split`), most alike first, `total`, `groups` (how many records are in some pair), `complete`, `examined`, `rows` |
| `embedding_outliers` | `k` (1 to 50, default 5), `limit` (1 to 1,000, default 50) | `k`, `outliers` (`id`, `distance` (one minus the cosine to its k-th nearest record), `nearest`, `split`), farthest first, `median` (of every examined row's distance), `complete`, `examined`, `rows` |
| `embedding_leakage` | `threshold` (default 0.95), `train` (the split trained on, default `train`), `limit` | `threshold`, `train`, `splits` (each split's count), `pairs` (`record`, `split`, `near` (the training record), `cosine`), most alike first, `total`, `leaked` (records of other splits with a near-copy in training), `complete`, `examined`, `rows`; a product with no splits answers `splits` {} and no pairs |

**Arithmetic,** in 64-bit floats with `math.sumprod`, `math.fsum` and `math.dist`. Rows are made unit length; cosine is their dot product.

- **The map (`pca`).** The mean and the leading eight principal components (fewer when there are fewer dimensions or rows) of a sample of the rows, evenly spaced, of at most `max(256, 2^19 / dimensions)` rows: by power iteration on the sample's covariance (computed whole when there are at most 1,024 dimensions, else applied without forming it), eight vectors together, orthonormalised each turn and rotated to the covariance's own axes by a small Jacobi solve (Rayleigh–Ritz), until they move less than 1e-9 or after 200 turns. Every row is projected on the first two. `explained` is each component's variance over the total. Signs are fixed so that each component's largest entry is positive.
- **Bounding the pair searches.** Each row also gets its coordinates on all the components and the length of what they leave out (the residual). For two unit rows, the distance in those coordinates, with the residual lengths as one more, is never more than their true distance, so a pair whose coordinates are farther apart than the threshold allows is ruled out without reading its rows. The rows are sorted by their first coordinate and each is compared with those within the threshold's distance along it; what is not ruled out is computed exactly. Nothing found is approximate.
- **What bounds it.** A search examines rows in a fixed shuffled order and stops after 20,000,000 comparisons of coordinates or 400,000 exact ones; a row is examined whole or not at all, so what is listed is exactly right for the rows examined, and `complete` says whether every row was. Duplicates and outliers examine every row; leakage the rows of the splits other than `train`.
- **Outliers** are the rows farthest from their k-th nearest neighbour (exact, by the same sorting: the search around a row stops when the first coordinate alone is farther than its k-th nearest so far).
- **Thin regions** are the map's cells (a `cells` by `cells` grid over its bounds) that hold some points but at most `thin` times the median count of the cells that hold any; each with its place, count and its records (at most 20), fewest first, at most 64 cells.
- **Colour.** `split` and `kind` are the records' own; `annotation:<task>` the value a frozen record carries for that task (a term, the terms joined, or its state when it has no value); `field:<key>` a key of a record's `meta` (a number is a number, anything else a category). At most 24 categories, the rest one `other`; a row with no value has the code 65535 or NaN.
- **Kept.** What is computed for a set (its unit rows, components, coordinates, sorted order, the searches' answers) is kept while its two files are unchanged, at most two sets and 400 MB, least recently used dropped.

## 5. The steps `embed` and `select`, and freezing a selection

**`embed`.** A dataset whose `run` has `step: "embed"`, `inputs: {"records": <a dataset>}`, and `settings`, every one optional: `model` and `profile` (the served alias; section 2's order otherwise), `prefix` (at most 1,000 characters), `dimensions` (1 to 4,096; Pumas truncates and renormalises), `name` (of the set; default the input's name), `batch` (1 to 256, default 32). Output: `embeddings/<name>.npy` and `.json`, with `source` naming the input and its run, `model` naming what answered (`name`, `model_id`, `profile`, `capability`, `via: "pumas"`), and nothing else in the product.

- **What is asked.** Text records (inline, or a UTF-8 file of at most 64 KiB) by `text_embedding` with `text_batch`, the prefix put before each text; PNG and JPEG images of at most 8 MiB by `multimodal_embedding` with `content_batch`, one image part an item. A batch is at most `batch` items, at most the advertised `input_count`, and for images at most the advertised `image_count` (4 without one) and 16 MiB. Options `{"kind": "embeddings", "dimensions": d}` only when `dimensions` is set; it is checked against an advertised `dimensions` bound when there is one. Records of other kinds, or that cannot be sent, are not embedded and are counted in `notes`.
- **Before anything is asked,** the step reads what the endpoint serves and fails, saying why, when the model is not served, the capability a kind of record needs is not available, or `dimensions` is past its bound. A dataset with records of a kind the model cannot embed fails before anything is asked unless it also has records it can; then those are noted.
- **The answer** must hold one finite vector per item, all of one length (`dimensions` when set). A refusal before the provider took it (`not_admitted`) is asked again twice, after 1 s and 2 s; anything else fails the step with the batch's first record.
- **Resumable.** Every batch answered is appended to `embeddings/.<name>.partial` (rows) and its ids to `.<name>.partial.json` (with the model, the input run, the prefix and the dimensions). When the dataset's last run failed, the build passes its output to the step, which takes the rows already answered from it when the input run, model, prefix and dimensions are the same, and asks only for the rest; the step says how many it took.
- **Progress** is the count of records embedded, in the existing form; the endpoint's address and version are kept in the run's record as for `generate`, never in the folder. Planning: without an endpoint the step is blocked as `generate` is.

**`select`.** A dataset whose `run` has `step: "select"`, `inputs: {"records": <a dataset>}`, `settings: {"records": [ids]}` (1 to 20,000 different ids): its product holds exactly those records of the input's product, in the input's order, each line as the input has it (its split and annotations kept), its file linked under `files/`, its hash computed when the input has none. An id the input does not have fails the step, naming the first. This is what a selection on the map becomes.

**Freeze** gains an optional setting `records` (1 to 20,000 ids): only those records of the input are taken, before the first task's states decide. "Freeze these" on the map opens the Freeze form with the dataset and the ids filled in.

`check` checks the settings of both steps; the schemas list them; both are planned, requested, approved, run and recorded like any build.

## 6. The page

**The dataset opened** (`#data/inside:<reference>`, spec-d1) gains a third mode beside Records and Files, **Map**, when `embeddings` lists a set for it. With several sets, a select names each (`holder · name · model`). A set whose records run is not the dataset's current product says so.

- **The map,** a canvas: the points, coloured by the choice (`Colour by`: none, split, kind, each annotation, each field), a legend with each category's count or the number scale's ends; the thin cells shaded; the selected record ringed, its most alike joined to it by lines. The wheel zooms about the pointer, dragging pans; "Reset view".
- **Hovering** a point shows its id and colour value in a tip; resting on it 300 ms shows the record in the viewer beside the map, with inside.js's viewers. A click opens it (pinned) and asks for its neighbours.
- **Choosing a region:** Box or Lasso (a toggle), then dragging. The chosen points are marked and counted. "New dataset from these" (title, name; Keep) keeps a `select` definition as an unsaved edit, as the other forms do, staying on the map; "Freeze these" opens the Freeze form filled in; "Clear".
- **Beside the map,** lists, each row a button that opens its record: **More like this** (the opened record's neighbours), **Duplicates** (threshold), **Outliers**, **Leakage** (when the records have splits; threshold and the training split), **Thin regions** (a cell's row selects its records). Each list is asked for when first shown and when its controls change.
- **The Embed form,** on the Data tab beside Import, Freeze and Generate: title, name, the dataset, the model (EmbeddingGemma 2 or the machine's setting, shown as what it resolves to now; or any served embedder), prefix (the default shown), dimensions (with the advertised bound), batch. It keeps an `embed` definition as an unsaved edit. With no endpoint, or none that embeds, it says so.
- **The endpoint's drawer** on Train shows the embedder (what the machine's setting or the default resolves to), and for the owner a select of the served embedders ("EmbeddingGemma 2 (default)" first) and the prefix, with Set.
- Every control is a button, select or field; the canvas has a text alternative and is reachable by Tab, with the arrow keys moving through the points nearest in the map. Light and dark from the tokens of `base.css`. Updating in place: the map's answers are not watched; a reading that changed something draws the view again in place keeping the set, colour, zoom, selection and the lists' controls; a timer or a return to the window with nothing changed touches nothing.

## 7. Slices

| | Slice | Files |
| --- | --- | --- |
| T5a | The contract, the reader and the six reads | `docs/contracts/project-folder.md`, `tuldok_project/embeddings.py` (new), `operations.py`, `service.py`, `tests/test_tuldok_project_curation.py` (new), the count of the table's rows in `tests/test_tuldok_project_service.py` |
| T5b | The default embedder, the settings, `embed`, `select`, freeze's `records` | `pumas_operations.py` (the `embeddings` result), `tuldok_project/pumas.py`, `local.py`, `steps.py`, `builds.py`, `plan.py`, `check.py`, `schemas/`, `operations.py`, `service.py`, `tests/fake_pumas_typed.py`, `tests/browser_fake_pumas.py`, `tests/test_tuldok_project_curation.py` |
| T5c | The page | `static/project-workspace/curation.js` (new), `inside.js`, `tabs.js` (the Embed button), `annotate.js` (Freeze filled in), `generate.js` (the embedder), `base.css`, `static/project-workspace.html`, `app.py` (the asset list), `tests/browser_project_workspace_curation.cjs` (new), its fixture |

## 8. Tests

**T5a and T5b, `tests/test_tuldok_project_curation.py`,** fixtures written by the test with the standard library:

- The contract: a set read; each rule broken once refused with its sentence (format, ids repeated, rows and shape disagreeing, a non-finite value, a zero row, a projection of the wrong shape, a bound lowered for the test).
- The map's components against the test's own arithmetic on a planted structure (points spread along two known orthogonal directions with known variances, and noise): the axes and the shares of variance; a script's projection used as given.
- Neighbours, duplicates, outliers and leakage on a fixture with planted near-duplicates, one far record and one validation record that is a near-copy of a training one, against a brute force the test computes; a budget lowered for the test gives `complete` false with exactly-right pairs for the rows examined; thin cells against the test's counting.
- The default embedder: EmbeddingGemma 2 chosen when served (by alias and by model id, the preferred id first), refused with the served embedders listed when not, never another model; the machine's setting and the definition's model in that order.
- `embed` against the fake endpoint, built for real by `builds.execute`: a text and image dataset embedded in batches, the requests' inputs, prefix and options as section 5 says, a valid product read back by the reads; a point cloud noted and not embedded; a `not_admitted` asked again; a failure part way and a second build that takes the answered rows and asks only for the rest; no endpoint, the plan says so. `select` and freeze's `records` built for real, with exactly the records chosen.
- The six reads and `set_embedder` in `project_folder`, not in `catalog`, its digest unchanged.

**T5c, `tests/browser_project_workspace_curation.cjs`,** on a fixture project (a frozen dataset with planted duplicates and one leaked validation record, embeddings written by a script), the fake endpoint, owner signed in, no GPU: the map drawn and coloured by split; a region chosen and kept as a new dataset whose definition holds exactly those records; Freeze filled in with them; the duplicates and the leaked record listed; more like this for an opened record; the Embed form showing EmbeddingGemma 2 as the default; light and dark at 1440 and 390 wide, no sideways overflow, no script error, nothing redrawn on a return to the window.

## 9. Out of scope

Computing embeddings in Tuldok; approximate nearest-neighbour indexes; UMAP or t-SNE in Tuldok (a script may write either as the projection); embeddings of sounds, point clouds and meshes through the endpoint (Pumas 0.8.0 embeds text and images only); colouring by an annotation that is not carried in the records (the working copy's annotations of a task); several sets on one map; clustering.

## As built

What differs from the text above, and what was found. Built on `feat/t5-curation` beside phase 3, which owns the Benchmarks and Analysis tabs and the Map's compare set; this phase touched `tabs.js` (the Embed button and its drawer, two lines), `base.css` (one block at its end), `operations.py`, `service.py`, `docs/contracts/project-folder.md` and the service test's count of operations (69 to 76) only where its own rows go.

### T5a, the contract, the reader and the reads

- **Record ids** in an index are 1 to 600 characters without control characters, not spec-d1's 1 to 200 of `A-Z a-z 0-9 . _ -`: a product read from its files names its records by their addresses (`notes/a.txt`), and those must be embeddable. Section 1 was corrected.
- **The blocking of the pair searches is a grid, not a sort.** As first built, rows were sorted by their first coordinate and each compared with those within the threshold along it. On clustered data (20 clusters, 256 dimensions) that window held most rows. The searches now bucket rows by up to five leading coordinates in cells twice the radius wide and look in the 2⁵ cells on the near side of each coordinate (exact: a row within the radius in every coordinate lies in one of them); the lower bound in all eight coordinates and the residual rules pairs out before the dot product. Outliers search the cells within the 90th percentile of the k-th nearest distance of 32 rows first, and fall back to the outward sort for a row whose k nearest are not all within it.
- **The budget is 20,000,000 coordinate comparisons or 400,000,000 values multiplied** (not 400,000 exact products: the cost of one depends on the dimensions), checked before each row; a row is examined whole. `complete` and `examined` say how far it got; a test lowers the budget and checks that the pairs listed are exactly the brute force's pairs of the rows examined (the shuffled order is `random.Random(f'{rows}:{dimensions}')`).
- **Measured** (this machine, CPU, pure Python, `math.sumprod` at about 8 to 12 ns a value), on the worst case the reader meets, clustered synthetic rows with no duplicate in them: 50,000 × 256 — reading and making unit 1.0 s, the map 2.4 s, more like this 0.18 s, duplicates 8.0 s and incomplete (634 rows examined), outliers 7.9 s (162), leakage 2.6 s (1,030 of 10,000 held-out rows); 10,000 × 768 — the map 8.8 s, duplicates 6.3 s (1,044), outliers 5.4 s (201), leakage complete in 1.0 s; 20,000 × 256 duplicates 6.8 s (1,587); 2,000 × 64 everything complete under 1 s. Each is computed once per set and kept. **The searches are complete for a few thousand rows only when the data is dense at the threshold's radius**; past that they list exact pairs for a shuffled sample of rows and say so. Without vectorised arithmetic this is the honest bound; an approximate index was left out (section 9).
- **Colour.** Numbers with at most 24 different values are drawn as categories (a split numbered 0, 1, 2 reads better so); more are a number scale. A category beyond the 24th is one `other`.
- **`embeddings`** is an operation outside the lock (it finds products under it, reads indexes after), not an `INSIDE_READS` row; `records_run` joined the service's product arguments. A set in a dataset that takes this one as an input whose index cannot be read is not listed (it cannot be told which records it describes); one in the dataset's own product is listed with its problem.
- **Tests:** `tests/test_tuldok_project_curation.py`, 13 for T5a (contract 3, components 3, searches 7). The catalog profile's digest is unchanged (110 operations).

### T5b, the embedder, `embed`, `select` and freeze's records

- **The default's match** is "the alias or `model_id` contains `embeddinggemma-2`" ignoring case; among those the `model_id` `unsloth/embeddinggemma-2-GGUF` (case ignored) first, then the endpoint's order; only entries with `text_embedding` or `multimodal_embedding` available and `embeddings_float32` out count. Several profiles of the default are not an error: the first is used. The refusal names every served embedder with its model id and profile.
- **The machine's setting** is `embedding_model`, `embedding_profile` and `embedding_prefix` in the settings file; `set_embedder` checks a named model against the endpoint (refused `not-found`, or `unavailable` with no endpoint) and writes an activity row `set` or `default`. A step reads the machine's setting at build time through the facts file (`<run>/embed.json`), so an `embed` that names no model is not reproducible from its definition alone; the index records what answered and `named_by` (`definition`, `setting` or `default`).
- **Requests.** `options` is always sent, `{"kind": "embeddings"}` and `dimensions` when set; `dimensions` is checked against an advertised bound when there is one and sent without one (the release accepts it on every embedder; spec-d5's rule that an option must be advertised was not applied here, since llama.cpp embedders may advertise none). Image batches stop short of 16 MiB of base64.
- **Rows are written in the order answered** (texts first, then images; on a resume, the rows taken first), and `records` follows that order; the contract allows any order.
- **A resume** takes rows only from the dataset's newest run, when it failed, and only when the input run, model, model id, profile, prefix and dimensions asked are all the same; the partial files are removed when the step ends, so a product holds only the set.
- **`pumas_operations`** gained the `embeddings` result (finite vectors of one length) beside `decisions`, additively; catalog mode never asks for it.
- **`select`** keeps a record's id when it is a list id and makes one (`id_from`) from an address otherwise, keeping the address in `meta.selected_from`. Freeze's `records` names input ids; one that is not in the input fails the step.
- **Not in the text:** `check` refuses `profile` without `model`; a step with no required setting still needs `"settings": {}`.
- **Tests:** 13 more in `tests/test_tuldok_project_curation.py` (the default embedder 3, settings 1, check 2, built for real against the fake 6, published 1). Project suite 799 OK (773 before, and these 26); agent interface 43 OK (4 skipped).

### T5c, the page

- **Map is a third mode of the opened dataset** (inside.js), shown when `embeddings` lists a readable set; its state is per dataset in page memory (the set, colour, view, tool, chosen, opened, each list's controls), not in the address: a reload opens on Records. The viewer beside the map is inside.js's, reading the record from the set's records run.
- **Tools** are Move, Box and Lasso (a toggle; Box first); a click that does not move opens the nearest point within 10 px. The wheel zooms about the pointer from 1 to 200 times. Keys: the arrows move a highlight to the nearest point in that direction (Enter opens it, Escape clears the choice), announced in a live region.
- **New dataset from these** is a form under the map (title, name, Keep), not a drawer, so the map stays; after Keep the line "Kept datasets/<name> as an unsaved edit" stays with the choice. **Freeze these** fills the Freeze form's slot (`annotate.js`'s new `fillFreeze`) and goes to `#data/new:freeze`, which shows "Only the N records chosen on the map" with a button to freeze every record instead; changing the dataset there drops them.
- **The embedder** is shown and set in the endpoint's drawer on Train (owner: a select with "EmbeddingGemma 2 (the default)" first, the prefix, Set the embedder); the Train section's rows were not changed. The Embed form's first model is "Default: <EmbeddingGemma 2 or the machine's> → <what it resolves to now>"; with the default chosen the definition names no model, and the prefix is written only when changed from the machine's.
- **Colours** are the dataviz reference palette's eight categorical hues as tokens `--cat-1` to `--cat-8` (light and dark steps); "other" and rows with no value are `--ink-3`; thin cells are washed with `--warn` at 14 %. Not run through the palette validator here (the palette is the validated reference instance).
- **The check,** `tests/browser_project_workspace_curation.cjs` (fixture `tests/project_curation_browser_fixture.py`, 244 texts in 16 dimensions with the plants; `browser_fake_pumas.py --embedders`): 7 PASS — the map drawn and coloured by split (pixels of the three colours counted on the canvas) and by a field; the three planted pairs, the leaked v001 alone, far01 the first outlier, more like this; a box of 97 records kept as a select of exactly the ids the test computes from `embedding_map`, and Freeze filled in and kept with them; the Embed form's default "EmbeddingGemma 2 → embeddinggemma-2 · embeddinggemma-2-gpu (unsloth/embeddinggemma-2-GGUF)"; nothing touched by a focus and a timer reading; light and dark at 1440 and 390, nothing in the map, its lists or the drawer overflowing. Regressions unchanged: `browser_project_workspace.cjs` (24 PASS), `_inside` (8), `_annotate` (11), `_endpoint` (8).
- **Found at 390 px:** the page is 553 to 554 px wider than the window on every tab, as phase 2 found (its header and strip); the check records it and asserts only the map, its lists and the drawer.
- **Not verified:** a real Pumas or a real EmbeddingGemma 2 (the owner's word is needed; no GPU was used); an embed built from the page (built in the unit tests against the fake); thin regions in the page (the fixture has none; tested in the reader); Lasso, Move and the wheel by a person (drawn and wired, not driven by the check); 50,000 points drawn in the browser (the map draws one arc a point, unmeasured past 244); a set whose records run is not current, and several sets of one dataset (the select is drawn, not exercised); colouring by an annotation the records carry in the page (tested in the reader); screen readers.
