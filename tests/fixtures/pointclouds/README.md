# Authored actual point-cloud fixtures

These are actual tiny ASCII PLY inputs authored for Tuldok's closed vertex-only
profile. `colored.ply` has four points, mixed float32/float64 XYZ and normals,
uint8 RGB, an unnormalized normal of magnitude two and a negative float32 zero.
`xyz.ply` has three float64 points, retaining a duplicate and negative zero.
Sidecars pin exact bytes/hash, declare m/mm, right-handed z-up authored frames,
and independent declared fixed train/validation families. Declarations are QA
claims, not verified rights or scientific independence.

Copy each matching pair as points.ply and points.json. Attribute/provenance-only
variants, 513-point/zero-span UI controls and decimal midpoint neighbors/ties are
explicitly source-derived authored tests, not additional producer or scan assets.
Originals remain unchanged. Actual external-reader oracles retain field dtypes,
native bytes, order, duplicate points, signed zero, units and immutable lineage.

See [point-cloud contract](../../../docs/contracts/point-clouds.md).
