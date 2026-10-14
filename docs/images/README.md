# Running-app screenshots

Captured on 2026-10-11 from upstream main
`1bb2c3ae9d08432c53ddf9d4bf77fa5f62ad318c`, using the supported `app.py`
server and `/workbench` route. Chromium 151.0.7922.173 rendered a 1600 × 1100
viewport at device scale 1. Files are direct JPEG quality-85 browser captures.

Launch from the tested checkout with an isolated sample-data directory:

```sh
python3 -u app.py --port 0 --data /tmp/tuldok-documentation-samples
```

Open the printed loopback URL with `/workbench` appended. The screenshot session
used a fresh isolated data directory, with these non-sensitive inputs:

- `dataset-workbench-text.jpg`: an authored `SAMPLE` workshop request, manually
  assigned the `scheduling` class and saved as a draft.
- `dataset-workbench-image.jpg`: the built-in `rectangles-v1` offline recipe,
  seed 42, count 3. The selected 128 × 128 image and its programmatically
  verified targets retain the recipe's authoritative name and status.
- `dataset-workbench-mesh.jpg`: the repository's authored analytic tetrahedron
  in `tests/fixtures/meshes/tetrahedron.ply` and its JSON sidecar, imported as
  `SAMPLE · Analytic tetrahedron`. Four vertices and four triangles render in
  three static projections; the imported record remains a draft.

The collection also contained a clearly labeled synthetic sequence from the
repository's `tests/test_sequences.py` fixture. Sequence inspection was checked
separately: it exposes transport metadata and frame indices, not animated
simulation or training qualification.

Existing disclosure controls were collapsed through their normal summary
controls. No application code, DOM text, CSS, or screenshot pixels were edited.
Images were visually inspected; the browser reported no JavaScript exceptions
and the server reported no tracebacks. Actual text save, offline generation,
asset loads and mesh projections were checked.

The dense filter panel pushes collection rows below the first viewport. The
small rectangle sample displays at its native size. These captures preserve
those current UI limitations. No private user data, secrets, camera feed,
pretrained inference or Pumas service was used. Audio is absent. Newer feature
branches were not integrated.
