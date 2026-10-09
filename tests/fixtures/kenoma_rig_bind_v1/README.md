# Representative Kenoma rig-v1 bind fixture

Consume `response.json.gz` directly. It is a gzip transport of the **exact**
UTF-8 string returned by the supported `evaluate(request)` WASM interface, with
no added newline, reformatting, decimation or coordinate conversion. `request.json`
is the exact input, including its trailing LF. All byte sizes and SHA-256 hashes
are in `manifest.json`. Extract with `gzip -dc response.json.gz > response.json`;
mesh importers should read `response.mesh.positions`, `.normals` and `.indices`.

- Protocol1, rig1, fixture1; headless crates0.1.0.
- Source checkpoint: `136f4947c7ef9bd2d4fe5cff09086489b0cb501d`.
- Retained WASM hash matches the actual tested checkpoint's browser receipts.
  Rust crates/Cargo inputs are unchanged at editor checkpoint
  `3e7ff0887d01a1f4c440d3808770ea3eac7ec8d4`.
- Freshly regenerated representative response, **not** a retained original wire
  capture. Two fresh Node/WASM processes produced byte-identical responses and
  gzip files. No simulation was run.
- 16 source nodes,15 source edges,46,728 vertices/normals,280,356 triangle indices,
  93,452 triangles. Positions/normals are arrays of XYZ triples; indices are a flat
  zero-based u32 triangle list. One closed connected manifold, outward winding.
- Right-handed character-local coordinates, +Y up, +Z head forward, metres;
  angles radians. Neutral head, default0.016m surface cell size. No scene transform.
- Exact response5,257,666bytes; gzip transfer1,508,798bytes. Request62bytes.

This is a schematic artistic mannequin, with no anatomical/medical inputs or
research artifacts. The returned `rig_id:1` belongs to its originating WASM
instance; it is not a portable rig handle. The mesh buffers are portable.

## Verification without Rust or compilation

From the repository root, run:

```sh
node assets/samples/rig_bind_v1/verify.mjs
```

This checks original/compressed hashes and sizes, counts, finite unit normals,
nondegenerate triangles, closed consistently wound topology, single component,
vertex-link cycles and positive signed volume. It only reads the committed
fixture. Tuldok should consume these bytes rather than access a Cargo directory
or regenerate physics/research data.

For maintainers with the already retained tested WASM/glue in
`browser/simple-graph/pkg/`, reproduction is:

```sh
node assets/samples/rig_bind_v1/generate.mjs /tmp/kenoma-bind-reproduced
```

The generator refuses a WASM hash mismatch rather than attaching stale source
provenance to a different build. No WASM build or Cargo access is needed to use
or verify the committed response fixture. The fixture directory contains only
this request/response pair, provenance and small reproduction/verification tools.
