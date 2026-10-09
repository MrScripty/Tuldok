# Independent preimplementation review

The exact base was 53f61bb7c9ed042fcb2ece9c89aac3c5926485ea; main remained
2fc4a46f12d73a0fa467d5482f68edb83d6df6af. Source ownership/migration and browser interaction reviews admitted the scoped
design before implementation. External-reader/lineage review began at design
time and admitted the refined design while implementation was underway, before
qualification. Final refined plan hash:
f63178d5788f125f3169885fb9ffd4a59e1c46a669b70e9f986b220a3a16470a.

Review refinements now explicit in the contract: nonempty human note; canonical
1–120 lineage IDs; injective domain-separated source and family tuple hashes;
four protected groups within the existing total 30 limit; sidecar-derived fixed
splits and export-only connected-conflict refusal; missing metadata cannot forget
lineage; new-kind support in shared snapshots/readers; signed-zero native data
and exact-bit float32 rejection; 512-point display ownership; second-owner raw
transfer creates drafts rather than local approval. Triangle support is retained.

This records design admission only. Final source/browser/consumer execution and
publication require separately sealed evidence outside the source tree.
