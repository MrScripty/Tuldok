# Bounded audio classification v1

The real local CPU recipe classifies one reviewed interval per recording.
Releases, Pipeline and Runs retain their existing custody and lifecycle owners;
`audio_training.py` owns the checked input, features, model and evaluator.
ASR remains unavailable.

`audio_classification_export.py` projects exactly one human-reviewed labelled
interval from each existing `audio_timed` recording. The annotation is retained
unchanged; `target_label` and frame/channel fields explicitly bind the model
target to it. The ZIP keeps byte-identical whole WAVs, original/PCM hashes,
source and annotation revisions, rights and the complete protected-family
snapshot. Release allocation includes unselected and retained deleted bridges.
One interval never becomes a separately independent recording.

Bounds are 6–256 recordings, 2–8 exact labels, every label in every split,
128–65,536 source frames and at most ten seconds per interval, 4,194,304 total
analyzed frames and 40 MiB original WAVs. Metadata is bounded to 7 MiB, the
complete ZIP and expanded payload to 48 MiB. Unsupported codecs retain the
existing PCM16 WAV rejection. Draft, transcript-only, multiple-interval and
stale selections do not silently lose records to become eligible.

`audio_training.inspect_release` independently checks exact assets, metadata,
reviewed target projection, class/JSONL mapping, bounds and frozen family
bridges. It uses the existing WAV parser. Only the custody-specific PostgreSQL
exception import moves into `AudioAssets.admit`; import/rollback semantics do
not change. `frozen_classification.py` is the shared complete-family reader,
preserving the text reader's previous validation meaning. Existing image
execution digests are untouched; new text adapter identities include the moved
reader. Old completed text runs remain interpreted by their saved identity.

The saved audio graph names `audio_classification`, recipe version 1. Its five
stages are release → validate → train → evaluate → publish, with `audio_export`
between validation and training. The only model parameter is `C`, a finite
number 0.01–100 (default 1). Graph edits, clones and invalid drafts use the
existing revision and typed validation contract. No new database schema exists.

The adapter measures mean, RMS, adjacent sign-bit changes
(zero is nonnegative), power-weighted spectral centroid normalized to Nyquist,
and four equal Nyquist-band power fractions. Input is the exact selected source
channel and half-open interval, converted from signed PCM16 by division by
32768. The rectangular-window NumPy rFFT uses its one-sided squared magnitudes
without doubling interior bins; all fractions and the centroid divide by their
sum. Bands include their lower edge and exclude their upper edge, except the
last band includes Nyquist. Odd lengths use their actual rFFT bin frequencies.
Silence gives zero centroid and band fractions. There is no resampling,
downmixing, cropping of the durable source or learned feature extraction.

Fitting uses train-only StandardScaler followed by existing pinned
scikit-learn 1.7.2 logistic regression, lbfgs, max_iter 200 and tolerance 1e-6.
Nonconvergence is failure. Coefficients and scaling statistics are data-only
JSON; a cold reader must reproduce fitted probabilities before publication.
The shared progress envelope records one fit as epoch 1; it does not imply one
optimizer iteration. There is no tuning or validation-based model selection.
Binary models retain one coefficient row and use a stable sigmoid; three to
eight classes retain one row per class and use softmax. Model readers reject
nonfinite or malformed arrays and never deserialize executable checkpoints.

Runs independently checks exact source/frame/channel predictions, classes,
metrics and artifact hashes before atomic publication. Validation metrics and
predictions are default; test artifacts require an explicit durable exposure
reason. Exposure uses the whole decoded-PCM/rate/channel family hash, so changing
an interval or RIFF metadata cannot present previously exposed audio as fresh.
There is no segment-based exemption. Correction edits the current annotation;
old release bytes, reviewed intervals and predictions remain immutable.

The existing one-worker supervisor and 600-second limit apply. Duplicate
submission keys reconcile the same durable receipt. Cancellation waits for
confirmed process-group cessation. A killed supervisor stops its actual audio
child; reopening classifies the attempt as interrupted without replay. Explicit
retry starts a new fit from verified frozen input and retains parent attempt
identity. Unconfirmed cessation blocks retry. Old completed image/text runs
remain readable without mutation; new audio graphs/runs require this application
version. Downgrade requires the existing stopped-writer complete backup, never
schema relabelling or deletion of newer records.

The optional existing scikit-learn 1.7.2/NumPy/SciPy/Pillow environment is probed
and observed with one native math thread; missing packages return unavailable.
The app imports no numerical runtime. No package, model or service is installed
automatically. Worker source identity pins this adapter, audio projection,
existing WAV parser, shared family reader and unchanged Workbench/JSON/process
primitives copied into the private attempt directory.

Tiny authored tones demonstrate custody and operation, never useful accuracy or
semantic independence. The first release/graph-only checkpoint remains recorded
separately in the source-bound screenshot gallery; it did not claim execution.
