# Implementation spec: a model's structure

This is phase 2 of [the training and curation plan](plan.md). It follows that plan's rule: a file contract, a reader and a view in Tuldok, and a thin optional helper. The readers follow [spec-d1.md](../definition-first-projects/spec-d1.md) and [spec-d2.md](../definition-first-projects/spec-d2.md): standard library only, nothing unpickled, nothing of the project's code run, nothing written, bounded reads, a damaged file refused and not a failure, reads outside the service lock. The page follows [spec-w4.md](../definition-first-projects/spec-w4.md): nothing is rebuilt by a timer or a return to the window.

**Owner, 2026-11-19:** "Tuldok needs live training views and model structure viwer."

**After this phase** a model's drawer shows, beside its Weights, how the model is built: its operations from input to output drawn left to right, its modules as groups that open and close, each operation's tensors linked to the Weights block, the drawing coloured by a figure per module (parameters, output size, how much the weights changed), and the graph of another model lined up with it, module by module. Tuldok draws what the project's training script recorded; it never runs the model.

## 1. The file: `model-graph.json`

Written by the project's script, where the model's code already runs, once, with an example input (plan, "Why the structure needs the training code"). It lies at the top of a run's product, or beside one of its weights files (spec-d2 section 1). Plain JSON, UTF-8, at most 32 MiB.

```json
{"format": "tuldok_model_graph_v1",
 "complete": true, "reason": null, "method": "torch.export",
 "torch": "2.8.0+cpu", "model": "mypackage.nets.Net",
 "inputs": [{"name": "x", "shape": [2, 1, 8, 8], "dtype": "float32"}],
 "tensors": {"stem.weight": {"shape": [4, 1, 3, 3], "dtype": "float32", "kind": "parameter"}},
 "nodes": [
   {"id": "x", "kind": "input", "operation": "input", "module": "", "tensors": [],
    "inputs": [], "outputs": [{"shape": [2, 1, 8, 8], "dtype": "float32"}], "attributes": {}},
   {"id": "conv2d", "kind": "operation", "operation": "aten.conv2d.default", "module": "stem",
    "tensors": ["stem.weight", "stem.bias"], "inputs": [{"shape": [2, 1, 8, 8], "dtype": "float32"}],
    "outputs": [{"shape": [2, 4, 8, 8], "dtype": "float32"}], "attributes": {"padding": [1, 1]}}],
 "edges": [{"from": "x", "to": "conv2d", "input": 0}],
 "modules": {"path": "", "class": "mypackage.nets.Net", "parameters": 1234, "children": [
   {"path": "stem", "class": "torch.nn.modules.conv.Conv2d", "parameters": 40, "children": []}]},
 "notes": []}
```

- `format` is `tuldok_model_graph_v1`. `complete` is false when only the module tree could be written; `reason` then says why (a sentence), and `nodes` and `edges` are empty. `method` is `torch.export`, `torch.fx` or `module-tree`. `torch` is the version that wrote it, `model` the class's import path (a name only: Tuldok never imports it).
- `inputs`: the example input's tensors, each `name`, `shape` and `dtype`.
- `tensors`: the model's parameters and buffers by the names of its `state_dict`, the names its weights file uses, each `shape`, `dtype` and `kind` (`parameter` or `buffer`).
- `nodes`, in an order where each node comes after the nodes it reads (the exported graph's order): `id` (unique), `kind` (`input`, `operation` or `output`), `operation` (the operator's name, `aten.conv2d.default`, or for a module traced whole by `torch.fx` the module's class), `module` (the path of the deepest module it ran in, `""` for the model itself), `tensors` (the names in `tensors` it reads), `inputs` and `outputs` (each `shape` and `dtype`, a list since an operation can take or give several; a value that is not a tensor is left out), and `attributes` (at most 16 of its other arguments, by name, each a number, a boolean, a short string, null or a list of at most 16 of those).
- `edges`: `from` a node `to` a node; `input` is the position of the value among the arguments of `to` that are nodes.
- `modules`: the tree of the model's modules from `named_modules`, each `path`, `class` (its import path), `parameters` (every parameter under it, counted once) and `children`.
- `notes`: sentences on what was left out (a truncated graph, an attribute dropped).

**Bounds,** which the helper keeps and the reader checks: 20,000 nodes, 100,000 edges, 20,000 modules, a module tree at most 64 deep, 100,000 tensors, 64 tensor names and 16 inputs or outputs per node, 16 axes per shape, 1,024 characters per string. A model whose exported graph has more than 20,000 nodes is written as its module tree with `complete` false and the reason.

## 2. The helper: `tuldok_log.graph.export_graph`

`tuldok_log` is the small package of the plan (decision 3). Phase 2 adds `tuldok_log/graph.py`; it imports the standard library and, inside `export_graph`, PyTorch.

`export_graph(model, example_inputs, path)` writes `model-graph.json` at `path` (a file, or a directory to write it in) and returns the dictionary written.

1. `torch.export.export(model, example_inputs)` (strict off, so a script's own Python is traced as written). Each `call_function` node becomes an operation; its module is the last entry of its `nn_module_stack`; its tensors are the parameters, buffers and constants it reads, by the names of the graph signature (which are the `state_dict` names); its shapes and types come from each node's `meta["val"]` (fake tensors: nothing is computed again).
2. If export fails: `torch.fx.symbolic_trace(model)`, the shapes from running `ShapeProp` once on the example input (a forward pass on the CPU or wherever the inputs are); a `call_module` node is one operation named by its module's class, with that module's tensors.
3. If both fail (a `forward` that branches on data values, say): the module tree only, `complete` false, `reason` naming both errors (their first line, at most 400 characters).

Never pickles, never imports anything of Tuldok's server, writes with `json.dump` to a temporary file in the same directory and renames it, so a reader never sees half a file.

## 3. Operations

Three reads, `inspect`, in `INSIDE_READS` like the others, in the `project_folder` profile and absent from `catalog` (whose digest is unchanged). Each takes `run`. The file is found at the top of the product, else beside the run's weights files (in their order); none is refused `not-found`.

| Operation | Arguments | Result |
| --- | --- | --- |
| `model_graph` | `depth` (0 to 64, default 1 when the graph has more than 200 operations, else 64), `open` and `close` (module paths, at most 2,000 each) | `path`, `format`, `complete`, `reason`, `method`, `torch`, `model`, `inputs`, `notes`, `depth`, `counts` (`nodes`, `edges`, `operations`, `modules`, `tensors` of the whole file), `modules` (the tree), `tensors`, `open` (the modules open in effect), and the graph folded: `nodes` and `edges` |
| `model_graph_overlay` | `kind`: `parameters`, `outputs`, `operations` or `change`; for `change`, `against`: `start` (the weights file's `initial-` file) or `run` (with `other_run`), and optionally `path` and `other_path` (weights files; default the first readable one) | `kind`, `unit`, `modules` ({path: number or null}), `nodes` ({id: number or null}), `low`, `high` (over the finite numbers of both), and for `change` `against` (`run`, `path`, `other_run`, `other_path`) |
| `model_graph_compare` | `other_run` | `modules`: every module path of either tree, in this tree's order then the other's, each `path`, `status` (`same`, `changed`, `added`: here only, `missing`: there only), `class`, `other_class`, `parameters`, `other_parameters`, `reshaped` (tensors directly in it whose shape differs: `name`, `shape`, `other_shape`), `only_here` and `only_there` (its own tensors on one side); `counts` by status |

**Folding.** A module's depth is its number of dotted parts (`""` is 0, `blocks` 1, `blocks.0.conv` 3). A module is open when it is in `open`, or when its depth is at most `depth` and it is not in `close`; the model itself is always open. An operation is shown when every module on its path is open; otherwise it is folded into the shallowest module on its path that is closed, shown as one node of kind `group`, id `module:<path>`. Inputs and outputs are always shown. A shown node carries `id`, `kind`, `label`, `module`, `class` (of its module), `operation` (operations), `tensors` (an operation's own; a group's, every tensor its operations read, at most 64, with `tensor_count`), `parameters` (the sum of the sizes of its tensors that are parameters, for a group its module's count), `inputs` and `outputs` (a group's: the values that cross into and out of it, at most 16 each), `operations` (1, or how many a group holds) and `first` (the position in the file of its first node). Shown nodes are in the order of `first`. Edges join the shown nodes of their two ends: an edge inside one group is dropped, edges between the same two shown nodes are one with `count`, and each carries `shape` and `dtype` of the first value it carries.

**Overlays.** `parameters`: a module's count from the tree; an operation's, the parameters among its tensors. `outputs`: the number of values an operation gives (the product of its outputs' shapes), a module's the sum over the operations in it. `operations`: how many operations run in a module (an operation's is 1). `change`: from `weights_compare` of spec-d2 (its bounds and refusals), the relative change of the tensors under a module (`sqrt(Σ difference_norm²) / sqrt(Σ other_norm²)` over them, the page's layer change of D2b) and of an operation's tensors; null where none is compared, where the other's norm is zero, or where a norm is not finite. "Under a module" means its own tensors and those of every module inside it.

**Comparing.** Modules are matched by path. `changed`: the class differs, or a tensor directly in it changed shape or is on one side only. A module whose children differ but whose own tensors and class are the same is `same`; its children say what changed.

**Refusals.** A file that is not UTF-8 JSON, not of the format, missing a key, of a wrong type, past a bound, with a duplicate node id, with an edge naming no node, or with a module tree not rooted at `""` is refused `unsupported` with a sentence saying what (a file over 32 MiB `too-large`). The parsed file is kept (8 files, least recently used dropped) while its size, time and inode are unchanged.

## 4. The page

In a model's drawer, a block **Structure** right after Weights, when one of the model's current products has `model-graph.json` (`model_graph` refused `not-found` for all of them: no block at all).

- **Head:** how it was written (`method`, `torch`), its counts, the example input's shapes; when not `complete`, the reason, and the module tree alone.
- **The drawing,** SVG, no library: left to right, ranks by the longest path from the inputs (an edge back to an earlier node is ignored in ranking and drawn as a curve), each rank's nodes ordered by the barycentre of their neighbours (four sweeps, down and up). Each node a box with its label (operation or module name), its output shape, and a mark for a group (how many operations). In a scrolling box of its own, so a wide graph never widens the drawer.
- **Folding:** a graph of more than 200 operations starts at depth 1, else open. A group pressed opens (one `model_graph`); the module outline under the drawing lists every module with its class and parameters, open or closed, as a tree whose rows open and close the module. "Open all" and "Fold to depth 1".
- **A node pressed** shows its details under the drawing: operation, module and class, inputs and outputs, attributes, and its tensors, each a link that opens that tensor in the Weights block above (its layer opened and scrolled to).
- **Colour by:** nothing, parameters, output size, change from the weights it started from (when kept), change from the model it derives from. The nodes are filled on a sequential scale (logarithmic for counts), a legend gives the ends; a node with no value is left plain.
- **Compare with:** the model it derives from and the models derived from it, when they have a graph. The other's drawing is shown under this one (the drawer is 420 px wide, so the two are stacked, one above the other, folded the same way), and both are marked from `model_graph_compare`: a module added (here only), missing (there only) or changed is outlined and named in a list of the differences.
- Every node is a focusable button (Enter or Space), with a text alternative. Light and dark from the tokens of `base.css`. Read again for the model on screen, the block resolves only once complete, and is put in place in one step with the person's place in it (folding, selection, colour, comparison) kept.

## 5. Slices

| | Slice | Files |
| --- | --- | --- |
| T2a | The contract, the helper, the reader and the operations | `docs/contracts/project-folder.md`, `tuldok_log/graph.py` (new), `tuldok_project/inside_graph.py` (new), `operations.py`, `service.py`, `tests/test_tuldok_project_model_graph.py` (new), `tests/test_tuldok_log_graph.py` (new), the count of the table's rows in `tests/test_tuldok_project_service.py` |
| T2b | The Structure block | `static/project-workspace/structure.js` (new), `weights.js` (opening a tensor from outside), `screens.js`, `adapter.js`, `base.css`, `static/project-workspace.html`, `app.py` (the asset list), `tests/browser_project_workspace_structure.cjs` (new), its fixture |

## 6. Tests

**T2a, `tests/test_tuldok_project_model_graph.py`,** on graph files the tests write by hand: a graph read whole; folding at depth 0, 1 and full, with `open` and `close`, against counts the test computes (nodes, edges merged with their count, an edge inside a group dropped, a group's crossing values and parameters); each overlay's arithmetic (parameters, outputs, operations, change against a known weights difference, against the start and another run); the comparison (same, changed by class, by shape, added, missing); every refusal (not JSON, wrong format, missing key, duplicate id, dangling edge, a bound lowered for the test, deep nesting); a module-tree-only file; the file found beside the weights; the three in `project_folder`, not in `catalog`, digest unchanged; the committed fixture graphs (written by the helper) read.

**`tests/test_tuldok_log_graph.py`,** with PyTorch on the CPU, skipped when it is absent: a nested model (a convolution stem, residual blocks of two convolutions with an add, an MLP head) exported whole: every parameter name in a node's `tensors` is in `state_dict`, every `state_dict` name is in `tensors`, the shapes are those of a forward pass, the add has two edges in, the module tree's counts are `sum(p.numel())`; a model whose `forward` branches on a value writes the module tree, `complete` false, with the reason; the file is JSON with no pickle; the node bound (lowered) falls back to the tree.

**T2b, `tests/browser_project_workspace_structure.cjs`,** on fixture products for a parent and a derived model (graphs written by the helper once and committed as test data, weights written with the standard library, the derived one with `initial-weights.npz`), owner signed in, no GPU, no PyTorch:

1. The derived model's drawer shows Structure after Weights, with the file's counts and the drawing; a model without a graph has no block.
2. Pressing a group opens it in place (more nodes, one `model_graph`, nothing else in the drawer rebuilt); the outline closes it again.
3. A node pressed shows its details; its tensor link opens that layer in the Weights block.
4. Colour by parameters and by change: the nodes' fills change and differ between nodes.
5. Compare with the parent: the changed and added modules are marked, as `model_graph_compare` says.
6. Light and dark, 1440 and 390 wide: no sideways overflow of the drawer or the page, no script error, no failed request; nothing redrawn on a return to the window.

## 7. Out of scope

Running the model, activations, profiling time per operation (a later field `seconds` on a node; nothing writes it yet), ONNX or TorchScript files, graphs of frameworks other than PyTorch, editing a model's structure, drawing more than two graphs at once.
