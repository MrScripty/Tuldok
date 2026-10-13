"""Bounded, independent stdlib importer for the v1 Tuldok dense3D pilot.

verify(directory) requires a completion manifest. The manifest= override is for
pre-publication orchestration only; its result does not publish or complete a run.
No Rheon code or numerical helper is imported. Requirements survive python -O.
"""
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import struct
import sys

BASE_COMMIT = "9cd4587a54befa61bdfddc8e35014bd3c34f02fb"
SCHEMA = "rheon.dense3d.accepted-sequence"
MANIFEST_LIMIT = 65536
FRAMES_LIMIT = 2097152
LINE_LIMIT = 262144
GEOMETRY = {
    "counts": [16, 8, 4], "origin_m": [0, 0, 0],
    "spacing_m": [0.0625, 0.125, 0.25], "axis_order": ["x", "y", "z"],
    "flattening": "i+nx*(j+ny*k)", "cell_offset": [0.5, 0.5, 0.5],
    "face_offsets": {"x": [0, 0.5, 0.5], "y": [0.5, 0, 0.5], "z": [0.5, 0.5, 0]},
    "field_shapes": {"velocity_x": [17, 8, 4], "velocity_y": [16, 9, 4],
                     "velocity_z": [16, 8, 5], "tracer": [16, 8, 4],
                     "fraction": [16, 8, 4], "pressure": [16, 8, 4]},
}
FIELD_TYPES = {"velocity_x": "f32", "velocity_y": "f32", "velocity_z": "f32",
               "tracer": "f32", "fraction": "f64", "pressure": "f64"}
UNITS = {"velocity": "m/s", "tracer": "dimensionless appearance", "fraction": "dimensionless",
         "pressure": "Pa", "time": "s", "divergence": "1/s", "pressure_residual": "m^3/s^2",
         "volume": "m^3", "mass": "kg"}
PRESSURE_SEMANTICS = "last accepted interval projection; constructor zero; not independently evolved endpoint"
CONFIG = {
    "carrier_density_kg_m3": 1000, "represented_density_kg_m3": 800, "requested_dt_s": 0.0625,
    "steps": 8, "pressure_implementation": "jacobi-pcg-v1", "initial_fraction": 0.5,
    "initial_slab_i": [4, 8], "initial_velocity_m_s": [0, 0, 0],
    "outward_speed_m_s": [[-0.25, 0.25], [0, 0], [0, 0]], "inlet_fraction": [[0, 0], [0, 0], [0, 0]],
    "carrier_id": "43", "liquid_id": "41", "initial_liquid_version": "0",
    "boundary_id": "47", "boundary_version": "0", "inlet_id": "53", "inlet_version": "0",
    "memory_limit_bytes": 16777216, "workspace_memory_limit_bytes": 16777216,
    "pressure_relative_residual": 1e-12, "pressure_absolute_residual": 1e-12,
    "pressure_divergence_limit": 1e-9, "pressure_max_iterations": 10000,
    "actual_divergence_limit": 1e-5, "max_courant": 1, "max_outward_courant": 1,
}
LIMITATIONS = [
    "fixed all-fluid constant-density carrier",
    "represented fraction donor transport",
    "no free-surface pressure/reconstruction/two-phase inertia/material calibration",
    "no multidirectional accuracy/performance/training qualification",
    "tracer appearance only",
]
DIAGNOSTICS = {"pressure_iterations", "pressure_residual_m3_s2", "carrier_divergence_s_inv",
               "liquid_divergence_s_inv", "volume_before_m3", "volume_after_m3", "mass_after_kg",
               "inward_m3", "outward_m3", "source_m3", "balance_m3", "rounding_budget_m3"}
HEX256 = re.compile(r"[0-9a-f]{64}\Z")
HEX160 = re.compile(r"[0-9a-f]{40}\Z")
U64 = re.compile(r"(?:0|[1-9][0-9]{0,19})\Z")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, name):
    require(type(value) in (int, float) and math.isfinite(value), "finite numeric " + name)
    return float(value)


def integer(value, low, high, name):
    require(type(value) is int and low <= value <= high, "integer " + name)
    return value


def exact(value, expected, name):
    if isinstance(expected, dict):
        require(type(value) is dict and value.keys() == expected.keys(), "keys " + name)
        for key in expected:
            exact(value[key], expected[key], name + "." + key)
    elif isinstance(expected, list):
        require(type(value) is list and len(value) == len(expected), "shape " + name)
        for index, item in enumerate(expected):
            exact(value[index], item, name + "[" + str(index) + "]")
    elif type(expected) in (int, float):
        require(number(value, name) == expected, "value " + name)
    else:
        require(type(value) is type(expected) and value == expected, "value " + name)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def _constant(value):
    raise ValueError("nonfinite JSON constant: " + value)


def _float(value):
    parsed = float(value)
    require(math.isfinite(parsed), "JSON float overflow")
    # A zero spelling can have any exponent; a nonzero mantissa may not silently underflow.
    mantissa = value.lower().split("e")[0].replace("-", "").replace(".", "")
    require(parsed != 0.0 or all(c == "0" for c in mantissa), "JSON float underflow")
    return parsed


def _int(value):
    require(len(value.lstrip("-")) <= 20, "JSON integer bound")
    parsed = int(value)
    require(abs(parsed) <= (1 << 64) - 1, "JSON integer overflow")
    return parsed


def parse(data):
    try:
        return json.loads(data, object_pairs_hook=_pairs, parse_constant=_constant,
                          parse_float=_float, parse_int=_int)
    except (UnicodeError, RecursionError, OverflowError, json.JSONDecodeError) as error:
        raise ValueError("invalid JSON: " + str(error)) from error


def bounded_read(path, cap):
    with path.open("rb") as stream:
        data = stream.read(cap + 1)
    require(len(data) <= cap, "file exceeds byte cap: " + path.name)
    return data


def stamp(value, ident, version, name):
    require(type(value) is dict and value.keys() == {"id", "version"}, "stamp keys " + name)
    for key in ("id", "version"):
        val = value[key]
        require(type(val) is str and U64.fullmatch(val) is not None and int(val) < 1 << 64,
                "canonical decimal u64 " + name + "." + key)
    require(value == {"id": ident, "version": str(version)}, "stamp continuity " + name)


def validate_manifest(manifest):
    fixed = {"schema": SCHEMA, "version": 1, "complete": True, "frame_count": 9,
             "frames_file": "frames.jsonl", "geometry": GEOMETRY, "field_types": FIELD_TYPES,
             "units": UNITS, "pressure_semantics": PRESSURE_SEMANTICS,
             "config": CONFIG, "limitations": LIMITATIONS}
    require(type(manifest) is dict and manifest.keys() == fixed.keys() | {
        "frames_sha256", "frames_bytes", "provenance"}, "manifest keys")
    for key, expected in fixed.items():
        exact(manifest[key], expected, "manifest." + key)
    integer(manifest["version"], 1, 1, "version")
    integer(manifest["frame_count"], 9, 9, "frame count")
    integer(manifest["frames_bytes"], 1, FRAMES_LIMIT, "frames bytes")
    require(type(manifest["frames_sha256"]) is str and HEX256.fullmatch(manifest["frames_sha256"]), "frames SHA256")
    provenance = manifest["provenance"]
    require(type(provenance) is dict and provenance.keys() == {
        "base_commit", "source_commit", "source_dirty", "source_sha256", "executable_sha256", "toolchain", "command", "build_command"}, "provenance keys")
    require(provenance["base_commit"] == BASE_COMMIT, "public base commit")
    require(type(provenance["source_commit"]) is str and HEX160.fullmatch(provenance["source_commit"]), "source commit")
    require(type(provenance["source_dirty"]) is bool, "source dirty boolean")
    hashes = provenance["source_sha256"]
    required = {"Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "examples/dense3d_sequence.rs",
                "tools/import_dense3d_sequence.py", "tools/export_dense3d_sequence.py",
                "src/dense3d_sequence.rs", "src/lib.rs", "src/liquid_step.rs", "src/simulation.rs",
                "src/geometry.rs", "src/pressure.rs"}
    require(type(hashes) is dict and required <= hashes.keys() and any(p.startswith("src/") and p.endswith(".rs") for p in hashes), "source hash coverage")
    for path, digest in hashes.items():
        require(type(path) is str and not PurePosixPath(path).is_absolute() and
                ".." not in PurePosixPath(path).parts and "\\" not in path and
                str(PurePosixPath(path)) == path and path not in ("", "."), "relative source path")
        require(type(digest) is str and HEX256.fullmatch(digest), "source SHA256")
    require(type(provenance["executable_sha256"]) is str and HEX256.fullmatch(provenance["executable_sha256"]), "executable SHA256")
    toolchain = provenance["toolchain"]
    require(type(toolchain) is dict and toolchain.keys() == {"rustc", "cargo"}, "toolchain keys")
    require(all(type(v) is str and v.strip() for v in toolchain.values()), "toolchain strings")
    build = ["cargo", "build", "--locked", "--no-default-features", "--example", "dense3d_sequence"]
    require(provenance["build_command"] in (build, build + ["--message-format=json-render-diagnostics"]),
            "core-only build command")
    command = provenance["command"]
    require(type(command) is list and 1 <= len(command) <= 128 and all(type(v) is str and v for v in command), "command strings")


def _fields(frame):
    fields = frame["fields"]
    require(type(fields) is dict and fields.keys() == FIELD_TYPES.keys(), "field names")
    for name, kind in FIELD_TYPES.items():
        values = fields[name]
        require(type(values) is list and len(values) == math.prod(GEOMETRY["field_shapes"][name]), "field shape " + name)
        for index, value in enumerate(values):
            native = number(value, name)
            if kind == "f32":
                try:
                    native = struct.unpack("<f", struct.pack("<f", native))[0]
                except (OverflowError, struct.error) as error:
                    raise ValueError("f32 overflow " + name) from error
                require(math.isfinite(native) and (native != 0 or value == 0), "finite native f32 " + name)
            values[index] = native
    return fields


def divergence(fields):
    maximum = 0.0
    nx, ny, nz = GEOMETRY["counts"]
    shapes = GEOMETRY["field_shapes"]
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                terms = []
                for axis, name in enumerate(("velocity_x", "velocity_y", "velocity_z")):
                    shape = shapes[name]
                    low = [i, j, k]
                    high = low.copy()
                    high[axis] += 1
                    a = low[0] + shape[0] * (low[1] + shape[1] * low[2])
                    b = high[0] + shape[0] * (high[1] + shape[1] * high[2])
                    terms.append((fields[name][b] - fields[name][a]) / GEOMETRY["spacing_m"][axis])
                maximum = max(maximum, abs(math.fsum(terms)))
    return maximum


def donor_oracle(step, i):
    return 0.5 * math.fsum(math.comb(step, k) * 0.25**k * 0.75**(step-k)
                          for k in range(step+1) if 4 <= i-k < 8)


def verify(directory, manifest=None):
    directory = Path(directory)
    if manifest is None:
        manifest = parse(bounded_read(directory / "run.json", MANIFEST_LIMIT))
    else:
        # Re-parse the bounded override to enforce the same strict native JSON gate.
        try:
            raw = json.dumps(manifest, allow_nan=False).encode()
        except (ValueError, TypeError, OverflowError) as error:
            raise ValueError("invalid manifest override") from error
        require(len(raw) <= MANIFEST_LIMIT, "manifest byte cap")
        manifest = parse(raw)
    validate_manifest(manifest)
    data = bounded_read(directory / "frames.jsonl", FRAMES_LIMIT)
    require(len(data) == manifest["frames_bytes"], "frames byte count")
    require(hashlib.sha256(data).hexdigest() == manifest["frames_sha256"], "frames SHA256 mismatch")
    require(data.endswith(b"\n"), "JSONL final newline")
    lines = data.split(b"\n")
    require(len(lines) == 10 and lines[-1] == b"", "exact nine frames")
    require(all(0 < len(line) <= LINE_LIMIT for line in lines[:-1]), "JSONL line byte cap")
    previous_volume = 0.125
    maxima = {"divergence_s_inv": 0.0, "binomial_fraction_error": 0.0, "velocity_error_m_s": 0.0, "first_pressure_error_pa": 0.0}
    volumes = []
    for index, line in enumerate(lines[:-1]):
        frame = parse(line)
        require(type(frame) is dict and frame.keys() == {
            "frame", "time_s", "dt_s", "carrier_stamp", "liquid_stamp", "fields", "diagnostics"}, "frame keys")
        integer(frame["frame"], index, index, "frame index")
        exact(frame["time_s"], index * 0.0625, "actual accepted time")
        exact(frame["dt_s"], 0.0625 if index else 0, "actual accepted dt")
        stamp(frame["carrier_stamp"], "43", index, "carrier")
        stamp(frame["liquid_stamp"], "41", index, "liquid")
        fields = _fields(frame)
        fractions = fields["fraction"]
        require(all(0 <= value <= 1 for value in fractions), "fraction bounds")
        error = max(abs(value - donor_oracle(index, cell % 16)) for cell, value in enumerate(fractions))
        require(error <= 2e-10, "every-cell binomial donor oracle")
        maxima["binomial_fraction_error"] = max(maxima["binomial_fraction_error"], error)
        measured_divergence = divergence(fields)
        require(measured_divergence <= 1e-5, "independent all-cell divergence")
        maxima["divergence_s_inv"] = max(maxima["divergence_s_inv"], measured_divergence)
        volume = math.fsum(fractions) * math.prod(GEOMETRY["spacing_m"])
        require(abs(volume - 0.125) <= 1e-12, "independent volume")
        require(abs(volume * 800 - 100) <= 1e-9, "independent mass")
        volumes.append(volume)
        if not index:
            require(frame["diagnostics"] is None, "constructor diagnostics")
            require(all(value == 0 for name, values in fields.items() if name != "fraction" for value in values), "constructor fields")
        else:
            diag = frame["diagnostics"]
            require(type(diag) is dict and diag.keys() == DIAGNOSTICS, "diagnostic keys")
            integer(diag["pressure_iterations"], 1 if index == 1 else 0, 10000, "pressure iterations")
            for name in DIAGNOSTICS - {"pressure_iterations"}:
                number(diag[name], name)
            require(0 <= diag["pressure_residual_m3_s2"] <= 1e-10, "pressure residual gate")
            for name in ("carrier_divergence_s_inv", "liquid_divergence_s_inv"):
                require(0 <= diag[name] <= 1e-5 and abs(diag[name] - measured_divergence) <= 1e-12, "independent divergence report")
            require(diag["volume_before_m3"] == previous_volume, "volume carry-forward")
            require(abs(diag["volume_after_m3"] - volume) <= 1e-12, "independent reported volume")
            require(abs(diag["mass_after_kg"] - volume * 800) <= 1e-9, "independent reported mass")
            require(diag["inward_m3"] == 0 and diag["source_m3"] == 0 and diag["outward_m3"] >= 0, "fixture boundary/source")
            before, after = diag["volume_before_m3"], diag["volume_after_m3"]
            outward, inward, source = diag["outward_m3"], diag["inward_m3"], diag["source_m3"]
            balance = after - before + outward - inward - source
            budget = (64 * sys.float_info.epsilon) * (abs(before) + abs(after) + outward + inward + abs(source))
            require(diag["balance_m3"] == balance and diag["rounding_budget_m3"] == budget and abs(balance) <= budget, "independent volume balance/budget")
            previous_volume = after
            for name in ("velocity_x", "velocity_y", "velocity_z"):
                velocity_error = max(abs(value - (0.25 if name == "velocity_x" else 0)) for value in fields[name])
                require(velocity_error <= 1e-8, "projected constant carrier")
                maxima["velocity_error_m_s"] = max(maxima["velocity_error_m_s"], velocity_error)
            if index == 1:
                error = max(abs(value + 1000 * 0.25 * ((cell % 16) * 0.0625) / 0.0625)
                            for cell, value in enumerate(fields["pressure"]))
                require(error <= 1e-5, "manufactured first interval pressure")
                maxima["first_pressure_error_pa"] = error
    centroid = math.fsum(value * ((cell % 16) + 0.5) * 0.0625
                         for cell, value in enumerate(fractions)) * math.prod(GEOMETRY["spacing_m"]) / volume
    require(abs(centroid - 0.5) <= 1e-10, "final centroid")
    return {"schema": SCHEMA, "version": 1, "frames": 9, "accepted_steps": 8, "time_s": 0.5,
            "volume_m3": volume, "mass_kg": volume * 800, "centroid_x_m": centroid,
            "all_frame_volumes_m3": volumes, "maxima": maxima, "limitations": LIMITATIONS}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: import_dense3d_sequence.py COMPLETED_RUN_DIRECTORY")
    print(json.dumps(verify(sys.argv[1]), indent=2, allow_nan=False))
