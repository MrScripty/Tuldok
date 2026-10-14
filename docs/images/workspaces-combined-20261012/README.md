# Combined image, text and audio workspace evidence

Clean runtime **83f53385a6812be4026302e7362a240b68ceb339**, 2026-10-12.
All inputs are authored fixtures exercising real imports, review, exports and bounded execution. Metrics describe these tiny authored corpora, not general model quality.

| Capture | Evidence |
| --- | --- |
| [Image results, 1440px](image-results-1440.jpg) | Actual scratch CPU run and artifacts |
| [Text Pipeline, 1440px](text-pipeline-1440.jpg) | Saved editable TF-IDF/Naive Bayes recipe |
| [Text results, 390px](text-results-390.jpg) | Real metrics and verified artifacts; test access remains locked |
| [Audio review, 390px](audio-reviewed-390.jpg) | Original WAV, source-frame annotation and channel controls |

Original JPEG85 bytes are preserved; [manifest](manifest.json) binds their SHA-256 hashes. Root visually inspected the desktop graph and narrow results/audio captures: controls/annotations readable, no horizontal overflow. These are scrolled screenshots, not full-page captures.

[Image receipt](image-receipt.json): 14 checks. [Text receipt](text-receipt.json): 14 checks. [Audio receipt](audio-receipt.json): 13 checks. Each ran on the clean runtime above, including native Chromium 200% zoom. Image/text receipts include 12 ordinary libc loopback-only transport canaries; this guard is not a direct-syscall security sandbox. Audio ran under the same inherited guard without an independent canary count claim.

[M1 receipt](m1-receipt.json): 18 fixture/navigation checks on clean e9809b5220f7ff03b3ce8795376e5379e9c9f4a1. The later runtime change only makes the export-warning notice modality-neutral.

The complete feature galleries retain their own clean source identities: [image](../workspaces-m2/README.md), [text](../workspaces-m3-text/README.md), [audio](../workspaces-audio/README.md).
