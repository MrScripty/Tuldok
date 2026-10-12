# Real WAV Data workflow

These original Chromium JPEG85 captures come from clean runtime/test commit
`2d5b8217967c6564b1b7089aef04be0b48c8c28a`. The scene contains only the
[authored stereo-impulse fixture](../../../tests/fixtures/workspaces/audio/README.md).
The [manifest](manifest.json) binds source identity, checks, exact image hashes,
reviewed record and frozen release. Images were copied without editing.

| State | Capture |
| --- | --- |
| Imported original PCM WAV, before review | [Desktop](audio-data-first-1440.jpg) |
| Saved channel/frame interval, class and human transcript | [Desktop](audio-reviewed-1440.jpg) · [390px narrow](audio-reviewed-390.jpg) |
| Real native Chromium 200% zoom, keyboard frame field focused | [Zoomed view](audio-native-200.jpg) |

The actual workflow imports a WAV, plays source channels, saves timed human
annotation, freezes original bytes with JSONL, rejects stale edits and reloads
durable history. Audio Pipeline/Runs execution and ASR remain unavailable.
[Qualification and launch details](../../plans/dataset-centered-workspaces/reports/m4-audio.md).
