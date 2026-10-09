"""Independently authored fixed-case contract assertions, never producer output."""
import hashlib
import json


def authored_controls(run, raw):
    frames = [json.loads(line) for line in raw.splitlines()]
    entries = []
    for j in range(1, 9):
        a, b = frames[j - 1], frames[j]
        entries.append({'start_frame': j - 1, 'end_frame': j, 'start_time_s': a['time_s'],
            'end_time_s': b['time_s'], 'dt_s': b['dt_s'], 'carrier_before': a['carrier_stamp'],
            'carrier_after': b['carrier_stamp'], 'liquid_before': a['liquid_stamp'], 'liquid_after': b['liquid_stamp'],
            'boundary_stamp': {'id': '47', 'version': '0'}, 'inlet_stamp': {'id': '53', 'version': '0'},
            'outward_speed_m_s': [[-0.25, 0.25], [0, 0], [0, 0]], 'inlet_fraction': [[0, 0], [0, 0], [0, 0]],
            'source_mode': 'none', 'source_rate_m3_s': 0, 'body_acceleration_m_s2': [0, 0, 0]})
    return {'schema': 'rheon.dense3d.interval-controls', 'version': 1,
        'run_sha256': hashlib.sha256(run).hexdigest(), 'frames_sha256': hashlib.sha256(raw).hexdigest(),
        'axis_order': ['x', 'y', 'z'], 'side_order': ['low', 'high'], 'speed_sign': 'positive outward normal',
        'units': {'time': 's', 'outward_speed': 'm/s', 'inlet_fraction': 'dimensionless', 'source_rate': 'm^3/s', 'body_acceleration': 'm/s^2'},
        'provenance': {'origin': 'independently_authored_contract_fixture', 'author': 'Tuldok contract fixture',
                       'source_note': 'Authored assertions bound to recorded pilot bytes; not emitted or executed controls.'},
        'intervals': entries}
