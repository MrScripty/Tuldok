# Real text workspace screenshots

Captured from clean source `a10f2cb9296e1070683352cd6e5b544729219738`
using Chromium 151.0.7922.173. These are actual local TF-IDF / MultinomialNB
results on 18 authored CC0 texts. Scores on these tiny, deliberately simple
examples demonstrate the workflow; they are not model-quality evidence.
The [manifest](manifest.json) preserves exact source, run/release IDs, original
image hashes, all 14 browser checks and resource/transport measurements.

| Workspace | Desktop | Narrow | Native 200% zoom |
| --- | --- | --- | --- |
| Data | [1440px](catalog-data-1440.jpg) | [390px](catalog-data-390.jpg) | [200%](data-native-200.jpg) |
| Pipeline | [1440px](pipeline-real-1440.jpg) | [390px](pipeline-real-390.jpg) | [200%](pipeline-native-200.jpg) |
| Results | [1440px](results-real-1440.jpg), [1024px](results-real-1024.jpg) | [390px](results-real-390.jpg), [metrics and artifacts](results-detail-390.jpg) | [200%](runs-native-200.jpg) |

[Admitted run observation](running-real-1440.jpg) · [Current-record correction](catalog-correction-1440.jpg)

Native zoom used Chromium keyboard zoom under an owned Xvfb display. Device
emulation was cleared; measured pixel ratio doubled and CSS viewport width
halved. The three views remained keyboard reachable without horizontal overflow.

The app, browser and trainer inherited a test libc guard allowing local TCP/UDP
and Unix sockets while denying ordinary external IPv4/IPv6 connect/sendto/DNS.
Twelve canaries passed. This is an ordinary transport qualification, not a
network-namespace or adversarial direct-syscall security sandbox.

All JPEGs are original browser captures at quality 85, copied byte-for-byte;
none were edited. [Verification report](../../plans/dataset-centered-workspaces/reports/m3-text.md).
