# Real image workspace screenshots

Captured from clean source `f725bd1806bfe5e27635eb817a403b602a14591a`
using Chromium 151.0.7922.173. These are actual CPU execution results on
12 authored CC0 drawings. They demonstrate workflow behavior, not model quality.
The [manifest](manifest.json) records exact run/release identity, screenshot
hashes, checks, viewport/zoom evidence and the offline transport limitation.

| Workspace | Desktop | Narrow | Native 200% zoom |
| --- | --- | --- | --- |
| Data | [1440px](catalog-data-1440.jpg) | [390px](catalog-data-390.jpg) | [200%](data-native-200.jpg) |
| Pipeline | [1440px](pipeline-real-1440.jpg) | [390px](pipeline-real-390.jpg) | [200%](pipeline-native-200.jpg) |
| Results | [1440px](results-real-1440.jpg), [1024px](results-real-1024.jpg) | [390px](results-real-390.jpg) | [200%](runs-native-200.jpg) |

[Active run](running-real-1440.jpg) · [Current-record correction](catalog-correction-1440.jpg)

Native zoom used Chromium keyboard zoom under Xvfb; measured device-pixel ratio
doubled and CSS viewport width halved. Device emulation was cleared first.
Zoom captures scroll to the active editor or metrics to show readable content.
All images are original JPEG quality 85, with no image editing.
