# Bounded audio classification v1

The first runnable checkpoint freezes real audio releases and edits a saved
typed graph. Execution deliberately returns `unavailable` until the separately
qualified CPU adapter exists. ASR is unavailable throughout this increment.

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

The admitted next checkpoint measures mean, RMS, adjacent sign-bit changes
(zero is nonnegative), power-weighted spectral centroid normalized to Nyquist,
and four equal Nyquist-band power fractions. Input is the exact selected source
channel and half-open interval, converted from signed PCM16 by division by
32768. The rectangular-window NumPy rFFT uses its one-sided squared magnitudes
without doubling interior bins; all fractions and the centroid divide by their
sum. Bands include their lower edge and exclude their upper edge, except the
last band includes Nyquist. Odd lengths use their actual rFFT bin frequencies.
Silence gives zero centroid and band fractions. There is no resampling,
downmixing, cropping of the durable source or learned feature extraction.

Planned fitting uses train-only StandardScaler followed by existing pinned
scikit-learn 1.7.2 logistic regression, lbfgs, max_iter 200 and tolerance 1e-6.
Nonconvergence is failure. Coefficients and scaling statistics are data-only
JSON; a cold reader must reproduce fitted probabilities before publication.
The initial checkpoint does not claim this fitting or its result lifecycle has
been implemented or qualified. Tiny authored tones demonstrate custody and
operation, never useful accuracy or semantic independence.
