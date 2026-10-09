"""Strict independent stdlib validator for proposed dense3D producer metadata v2.

This does not upgrade a v1 run or imply adoption by the current Tuldok reader.
The unchanged v1 consumer checks the original numerical contract against an
explicit, in-memory downgraded manifest. No completion file is written here.
The manifest override is only for caller-controlled pre-publication checking.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unicodedata

import rheon_sequence_contract as v1

SCHEMA = v1.SCHEMA
CONTROLS_SCHEMA = "rheon.dense3d.interval-controls"
VERSION = 2
CONTROLS_LIMIT = 65536
MANIFEST_LIMIT = v1.MANIFEST_LIMIT
SOURCE_RATE_KEY = "source_rate_m3_s"  # Confirmed by Tuldok's source-pinned authored fixture.
CONTROLS_MANIFEST_KEYS = {"controls_file", "controls_bytes", "controls_sha256"}
BINDING_KEYS = {"schema", "version", "geometry", "field_types", "units",
                "pressure_semantics", "config", "limitations", "provenance"}
CONTROLS_KEYS = {"schema", "version", "run_binding", "frames_sha256", "axis_order",
                 "side_order", "speed_sign", "units", "provenance", "intervals"}
CONTROL_UNITS = {"time": "s", "outward_speed": "m/s", "inlet_fraction": "dimensionless",
                 "source_rate": "m^3/s", "body_acceleration": "m/s^2"}
INTERVAL_KEYS = {"start_frame", "end_frame", "start_time_s", "end_time_s", "dt_s",
                 "carrier_before", "carrier_after", "liquid_before", "liquid_after",
                 "boundary_stamp", "inlet_stamp", "outward_speed_m_s", "inlet_fraction",
                 "source_mode", SOURCE_RATE_KEY, "body_acceleration_m_s2"}
require = v1.require


def typed_equal(actual, expected, name):
    """Recursive equality that never treats an int, float, or bool as another type."""
    require(type(actual) is type(expected), "type " + name)
    if type(expected) is dict:
        require(actual.keys() == expected.keys(), "keys " + name)
        for key in expected:
            typed_equal(actual[key], expected[key], name + "." + key)
    elif type(expected) is list:
        require(len(actual) == len(expected), "shape " + name)
        for index, value in enumerate(expected):
            typed_equal(actual[index], value, name + "[" + str(index) + "]")
    elif type(expected) in (int, float):
        v1.number(actual, name)
        require(actual == expected, "value " + name)
    else:
        require(actual == expected, "value " + name)


def provenance_text(value, name):
    require(type(value) is str and 1 <= len(value) <= 1000, "provenance text " + name)
    require(all(unicodedata.category(c) not in {"Cc", "Cs"} for c in value),
            "provenance control character " + name)


def downgraded_manifest(manifest):
    """Validate the explicit version switch and preserve all original v1 values."""
    require(type(manifest) is dict, "manifest object")
    require("version" in manifest, "manifest version")
    v1.integer(manifest["version"], VERSION, VERSION, "v2 version")
    require(CONTROLS_MANIFEST_KEYS <= manifest.keys(), "controls manifest keys")
    require(manifest["controls_file"] == "controls.json" and type(manifest["controls_file"]) is str,
            "controls fixed file")
    v1.integer(manifest["controls_bytes"], 1, CONTROLS_LIMIT, "controls bytes")
    require(type(manifest["controls_sha256"]) is str and v1.HEX256.fullmatch(manifest["controls_sha256"]),
            "controls SHA256 format")
    old = {key: copy.deepcopy(value) for key, value in manifest.items()
           if key not in CONTROLS_MANIFEST_KEYS}
    old["version"] = 1
    v1.validate_manifest(old)  # Checks the complete original key set and all v1 fields.
    require("tools/import_dense3d_controls.py" in manifest["provenance"]["source_sha256"],
            "v2 validator source hash coverage")
    return old


def validate_controls(controls, manifest, frames):
    """Validate one complete sidecar against typed manifest copies and raw frames."""
    downgraded_manifest(manifest)
    require(type(controls) is dict and controls.keys() == CONTROLS_KEYS, "controls keys")
    typed_equal(controls["schema"], CONTROLS_SCHEMA, "controls.schema")
    v1.integer(controls["version"], VERSION, VERSION, "controls version")
    binding = {key: manifest[key] for key in BINDING_KEYS}
    typed_equal(controls["run_binding"], binding, "run_binding")
    typed_equal(controls["frames_sha256"], manifest["frames_sha256"], "controls.frames_sha256")
    typed_equal(controls["axis_order"], ["x", "y", "z"], "controls.axis_order")
    typed_equal(controls["side_order"], ["low", "high"], "controls.side_order")
    typed_equal(controls["speed_sign"], "positive outward normal", "controls.speed_sign")
    typed_equal(controls["units"], CONTROL_UNITS, "controls.units")
    provenance = controls["provenance"]
    require(type(provenance) is dict and provenance.keys() == {"origin", "author", "source_note"},
            "controls provenance keys")
    typed_equal(provenance["origin"], "producer_emitted", "controls.provenance.origin")
    for key in ("author", "source_note"):
        provenance_text(provenance[key], key)
    require(type(frames) is list and len(frames) == 9, "controls adjacent frame roster")
    intervals = controls["intervals"]
    require(type(intervals) is list and len(intervals) == 8, "eight ordered controls intervals")
    for index, interval in enumerate(intervals, 1):
        require(type(interval) is dict and interval.keys() == INTERVAL_KEYS, "interval keys")
        v1.integer(interval["start_frame"], index - 1, index - 1, "interval start_frame")
        v1.integer(interval["end_frame"], index, index, "interval end_frame")
        before, after = frames[index - 1], frames[index]
        typed_equal(interval["start_frame"], before["frame"], "adjacent start frame")
        typed_equal(interval["end_frame"], after["frame"], "adjacent end frame")
        for key, actual in (("start_time_s", before["time_s"]), ("end_time_s", after["time_s"]),
                            ("dt_s", after["dt_s"])):
            v1.number(interval[key], "interval." + key)
            typed_equal(interval[key], actual, "adjacent " + key)
        require(interval["end_time_s"] - interval["start_time_s"] == interval["dt_s"],
                "accepted interval clock difference")
        for field, ident, prefix in (("carrier_stamp", "43", "carrier"), ("liquid_stamp", "41", "liquid")):
            for suffix, frame, version in (("before", before, index - 1), ("after", after, index)):
                key = prefix + "_" + suffix
                v1.stamp(interval[key], ident, version, "interval." + key)
                typed_equal(interval[key], frame[field], "adjacent " + key)
        v1.stamp(interval["boundary_stamp"], "47", 0, "interval boundary")
        v1.stamp(interval["inlet_stamp"], "53", 0, "interval inlet")
        # The proposed fixed examples use numeric zero and decimal nonzero
        # spellings; both integer and float numbers are allowed here, never bool.
        v1.exact(interval["outward_speed_m_s"], [[-.25, .25], [0, 0], [0, 0]], "interval outward speed")
        v1.exact(interval["inlet_fraction"], [[0, 0], [0, 0], [0, 0]], "interval inlet fraction")
        typed_equal(interval["source_mode"], "none", "interval source_mode")
        v1.exact(interval[SOURCE_RATE_KEY], 0, "interval absent source rate")
        v1.exact(interval["body_acceleration_m_s2"], [0, 0, 0], "interval body acceleration")
    return {"controls_schema": CONTROLS_SCHEMA, "controls_version": VERSION,
            "control_intervals": len(intervals), "controls_provenance": copy.deepcopy(provenance)}


def _manifest_override(manifest):
    try:
        raw = json.dumps(manifest, allow_nan=False).encode("utf8")
    except (ValueError, TypeError, OverflowError, UnicodeError) as error:
        raise ValueError("invalid v2 manifest override") from error
    require(len(raw) <= MANIFEST_LIMIT, "manifest byte cap")
    return v1.parse(raw)


def verify(directory, manifest=None):
    directory = Path(directory)
    if manifest is None:
        manifest = v1.parse(v1.bounded_read(directory / "run.json", MANIFEST_LIMIT))
    else:
        manifest = _manifest_override(manifest)
    old = downgraded_manifest(manifest)
    controls_raw = v1.bounded_read(directory / "controls.json", CONTROLS_LIMIT)
    require(len(controls_raw) == manifest["controls_bytes"], "controls byte count")
    require(hashlib.sha256(controls_raw).hexdigest() == manifest["controls_sha256"], "controls SHA256 mismatch")
    controls = v1.parse(controls_raw)
    frames_raw = v1.bounded_read(directory / "frames.jsonl", v1.FRAMES_LIMIT)
    require(len(frames_raw) == manifest["frames_bytes"], "frames byte count")
    require(hashlib.sha256(frames_raw).hexdigest() == manifest["frames_sha256"], "frames SHA256 mismatch")
    # The original consumer reads and verifies these original bytes itself; it
    # receives only an explicit temporary manifest object, never a written v1 file.
    result = v1.verify(directory, manifest=old)
    require(frames_raw.endswith(b"\n"), "JSONL final newline")
    lines = frames_raw.split(b"\n")
    require(len(lines) == 10 and lines[-1] == b"", "exact nine raw frames")
    frames = [v1.parse(line) for line in lines[:-1]]
    result.update(validate_controls(controls, manifest, frames))
    result.update(version=VERSION, controls_file="controls.json",
                  controls_bytes=len(controls_raw), controls_sha256=manifest["controls_sha256"])
    return result


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: import_dense3d_controls.py COMPLETED_V2_RUN_DIRECTORY")
    print(json.dumps(verify(sys.argv[1]), indent=2, allow_nan=False))
