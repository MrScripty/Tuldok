# Native MAC numerical consumer, version1

`native_sequence_dataset.NativeSequenceDataset` is the local NumPy2.5.3 consumer of human-reviewed, sequence-only canonical releases. It supports the existing fixed16x8x4 constructor plus8 accepted steps (nine frames), retained v1 bytes and explicitly source-derived v2 compatibility fixtures. It neither runs physics nor defines a training objective. The exact supplied release SHA256 must come from the trusted release owner/download ID; a hash invented alongside a packet does not authenticate its producer, author, rights or physical independence.

```python
from native_sequence_dataset import NativeSequenceDataset
samples = NativeSequenceDataset("release.zip", sha256=release_id,
                                split="train", window_frames=3)
sample = samples[0]
vx = sample["fields"]["velocity_x"]  # [3,17,8,4], float32; vx[t,i,j,k]
pressure = sample["fields"]["pressure"]  # [3,16,8,4], float64
samples.write_npz("native-sample.npz", 0)
```

Default `window_frames=9` returns whole trajectories; explicit1..9 returns all contiguous windows in frozen manifest record order and ascending global start frame. The selected split is required. Window sampling never assigns splits or establishes independent examples. Keep source record/family identities when splitting or evaluating; related windows must stay within their original component. An empty requested split has no samples; it is never filled from train.

All six fields remain named and separate with `[time,x,y,z]` axes. The x-fastest wire index `i+nx*(j+ny*k)` maps exactly to `[t,i,j,k]`; no interpolation, spatial centering, normalization, image projection or velocity concatenation occurs. Native f32 rounding/signed zero and f64 values are retained. Original geometry/shapes/axis order, face/cell offsets, origin/spacing, units, pressure semantics, time/dt, diagnostics, raw-line hashes and stamps remain in sample metadata. Constructor0 has no previous accepted interval. The first interval in a window starting after0 keeps its original preceding frame even when that frame is outside the numerical window. V2 controls remain hash-bound wire declarations with their original global frame-ending associations and provenance; v1 exposes no emitted controls.

`range_frame_mask` has boolean shape `[range,time]` in original human range order, with inclusive global frame coverage. Exact labels, rationale and original full-range/source/endpoint anchors remain in `metadata.record.annotation`; overlap is retained. Empty ranges/false coverage do not mean a physical negative. No class indices, project taxonomy, automatic review or force/mask/scientific ground truth are inferred.

Admission captures bounded original release bytes once. Later input-path replacement or caller edits to sample arrays/metadata cannot change subsequent samples. Before exposing any sample, the reader checks the full hash, safe unique stored ZIP members and preflighted directory count, exact manifest/JSONL association, human review/source revisions, original bundle hashes and source-pinned numerical validation, canonical metadata/index/targets and raw-derived initial-family/trajectory groups. Producer validation necessarily parses transient numerical JSON; only NumPy tensor materialization is deferred until requested, without an eager tensor cache.

New sequence-only canonical exports include the existing allocator's declared `protected_components` snapshots and per-record `export_group`. Reader checks complete known parent references, exact selected snapshots, component IDs, connected relationships, fixed/deleted lineage and split boundaries. This proves the declared known graph, not authenticity or completeness of unknown upstream evidence. Mixed/nonsequence canonical exports retain their existing strict importer contracts. Older sequence-only releases without these fields are readable only with exactly one populated split and an explicit missing-unselected-bridge-proof limitation; old frozen bytes remain unchanged.

Limits:64MiB physical/logical release,8MiB manifest and each split JSONL,256KiB JSONL line,1..64 selected sequences,5000 declared context members,40MiB selected raw bundles, existing run/controls64KiB and frames2MiB bounds. ZIP64, multi-disk, compressed/encrypted members, comments/extras, unknown/duplicate/unsafe members and mixed record kinds are unsupported. SHA/split/window/index inputs have strict types; booleans are not integers. A related unknown deleted lineage or missing parent blocks this consumer, without changing the stored release.

CLI inspection and derived sample export:

```sh
python native_sequence_dataset.py release.zip --sha256 "$RELEASE_ID" --split train --window-frames 3 --sample 0 --npz native-sample.npz
```

The JSON report shows source metadata, field shapes/dtypes, global frames/time and human coverage. The atomic `native_mac_sample_v1` NPZ has exactly the six numerical field names plus `frame_indices`int64, `time_s`/`dt_s`float64, `range_frame_mask`bool and `metadata_utf8`uint8 UTF8 JSON bytes. It has no object arrays and is readable with `numpy.load(path,allow_pickle=False)`. Complete logical/output bound16MiB includes NPY/ZIP overhead. Failed writes/publication clean up the sibling temporary and preserve existing output; input ZIP aliases cannot be overwritten. Keep the original canonical/raw release beside derived samples.

Optional Torch2.8 CPU DataLoader iteration uses explicit preserve-sample list collation, since human ranges and None interval/control entries vary. It qualifies map-style iteration only, not default minibatching, a model/trainer contract or training success. A real downstream objective/taxonomy and meaningfully independent initial/configuration families remain separate inputs. Duplicating fixtures, slicing time or changing provenance is not physical diversity. UI remains provisional.
