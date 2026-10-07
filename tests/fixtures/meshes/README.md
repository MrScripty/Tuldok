# Authored real PLY inputs

These are small actual ASCII PLY 1.0 geometry files authored for Tuldok's closed
profile, not producer snapshots, parser mocks, scanned assets or Rheon outputs.
Tetrahedron: four unit-axis vertices, four outward triangles, bounds [0,0,0]
to [1,1,1], volume 1/6 m³ (oracle only, importer makes no volume claim).
Open surface: four vertices, two triangles, bounds [0,0,0] to [2,2,0]; the
provided float normals have magnitude two and must remain unchanged.
Sidecars declare right-handed fixture-world coordinates, z up and metres.
Fixture geometry is project-authored test data distributed on project terms.

Select or copy each matching pair as mesh.ply and mesh.json. Sidecars pin exact
file bytes/SHA256. Definition authority: [original PLY format description](https://sites.cc.gatech.edu/projects/large_models/ply.html).
The consumer only claims its [bounded profile](../../../docs/contracts/static-mesh.md).
No third-party meshes were incorporated: the inspected tinyply README's
software dedication does not explicitly establish rights to its mesh assets.
