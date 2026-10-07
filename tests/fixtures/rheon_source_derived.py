"""Synthetic import fixtures only: never launches physics or comparison cases."""
import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import rheon_sequence_contract as consumer


def synthetic_frames():
    frames = []
    for step in range(9):
        fields = {}
        for name, shape in consumer.GEOMETRY["field_shapes"].items():
            fields[name] = [0.25 if step and name == "velocity_x" else 0.0] * math.prod(shape)
        profile = [0.5 * sum(math.comb(step, k) * (1 / 4)**k * (3 / 4)**(step-k)
                             for k in range(step+1) if 4 <= i-k < 8) for i in range(16)]
        fields["fraction"] = profile * 32
        if step == 1:
            fields["pressure"] = [-250.0 * (i % 16) for i in range(512)]
        diag = None
        if step:
            diag = {"pressure_iterations": 1 if step == 1 else 0,
                    "pressure_residual_m3_s2": 0.0,
                    "carrier_divergence_s_inv": 0.0, "liquid_divergence_s_inv": 0.0,
                    "volume_before_m3": 0.125, "volume_after_m3": 0.125, "mass_after_kg": 100.0,
                    "inward_m3": 0.0, "outward_m3": 0.0, "source_m3": 0.0, "balance_m3": 0.0,
                    "rounding_budget_m3": 64 * sys.float_info.epsilon * 0.25}
        frames.append({"frame": step, "time_s": step * 0.0625, "dt_s": 0.0625 if step else 0.0,
                       "carrier_stamp": {"id": "43", "version": str(step)},
                       "liquid_stamp": {"id": "41", "version": str(step)},
                       "fields": fields, "diagnostics": diag})
    return frames


def synthetic_manifest(data):
    paths = ["Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "examples/dense3d_sequence.rs",
             "tools/import_dense3d_sequence.py", "tools/export_dense3d_sequence.py", "src/lib.rs",
             "src/dense3d_sequence.rs", "src/liquid_step.rs", "src/simulation.rs",
             "src/geometry.rs", "src/pressure.rs"]
    return {"schema": consumer.SCHEMA, "version": 1, "complete": True, "frame_count": 9,
            "frames_file": "frames.jsonl", "frames_sha256": hashlib.sha256(data).hexdigest(),
            "frames_bytes": len(data), "geometry": copy.deepcopy(consumer.GEOMETRY),
            "field_types": copy.deepcopy(consumer.FIELD_TYPES), "units": copy.deepcopy(consumer.UNITS),
            "pressure_semantics": consumer.PRESSURE_SEMANTICS, "config": copy.deepcopy(consumer.CONFIG),
            "limitations": copy.deepcopy(consumer.LIMITATIONS),
            "provenance": {"base_commit": consumer.BASE_COMMIT, "source_commit": "1" * 40,
                           "source_dirty": False, "source_sha256": {path: "2" * 64 for path in paths},
                           "executable_sha256": "3" * 64, "toolchain": {"rustc": "rustc synthetic", "cargo": "cargo synthetic"},
                           "build_command": ["cargo", "build", "--locked", "--no-default-features", "--example", "dense3d_sequence"],
                           "command": ["target/debug/examples/dense3d_sequence", "fresh-synthetic-directory"]}}
