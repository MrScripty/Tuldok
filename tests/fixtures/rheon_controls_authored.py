"""Synthetic controls transport fixtures, NOT actual producer/physics evidence.

The schema requires the origin literal producer_emitted. Here that is only an
unauthenticated schema declaration; author/source_note and toolchain identify
these constructed bytes explicitly as synthetic. Never use them for V2/V4
actual-packet acceptance or infer a completed producer execution from them.
"""
import copy
import hashlib
import json

from fixtures.rheon_source_derived import synthetic_frames, synthetic_manifest
import rheon_controls_contract as controls_contract


def fixture(mutate_controls=None, mutate_manifest=None):
    frames = synthetic_frames()
    frames_raw = b''.join(json.dumps(row, separators=(',', ':')).encode() + b'\n' for row in frames)
    manifest = synthetic_manifest(frames_raw)
    manifest['version'] = 2
    manifest['provenance']['source_sha256']['tools/import_dense3d_controls.py'] = '2' * 64
    controls = {'schema': controls_contract.CONTROLS_SCHEMA, 'version': 2,
                'run_binding': {key: copy.deepcopy(manifest[key]) for key in controls_contract.BINDING_KEYS},
                'frames_sha256': manifest['frames_sha256'], 'axis_order': ['x', 'y', 'z'],
                'side_order': ['low', 'high'], 'speed_sign': 'positive outward normal',
                'units': copy.deepcopy(controls_contract.CONTROL_UNITS),
                'provenance': {'origin': 'producer_emitted', 'author': 'Synthetic Tuldok test constructor',
                    'source_note': 'Authored synthetic schema fixture; no producer execution or authenticity evidence.'},
                'intervals': []}
    for before, after in zip(frames, frames[1:]):
        controls['intervals'].append({'start_frame': before['frame'], 'end_frame': after['frame'],
            'start_time_s': before['time_s'], 'end_time_s': after['time_s'], 'dt_s': after['dt_s'],
            'carrier_before': before['carrier_stamp'], 'carrier_after': after['carrier_stamp'],
            'liquid_before': before['liquid_stamp'], 'liquid_after': after['liquid_stamp'],
            'boundary_stamp': {'id': '47', 'version': '0'}, 'inlet_stamp': {'id': '53', 'version': '0'},
            'outward_speed_m_s': [[-.25, .25], [0, 0], [0, 0]], 'inlet_fraction': [[0, 0], [0, 0], [0, 0]],
            'source_mode': 'none', 'source_rate_m3_s': 0, 'body_acceleration_m_s2': [0, 0, 0]})
    if mutate_controls:
        mutate_controls(controls)
    controls_raw = json.dumps(controls, separators=(',', ':'), allow_nan=True).encode()
    manifest.update(controls_file='controls.json', controls_bytes=len(controls_raw),
                    controls_sha256=hashlib.sha256(controls_raw).hexdigest())
    if mutate_manifest:
        mutate_manifest(manifest)
    return json.dumps(manifest, separators=(',', ':'), allow_nan=True).encode(), frames_raw, controls_raw
