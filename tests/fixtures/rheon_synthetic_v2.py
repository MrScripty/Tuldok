"""Source-derived synthetic v2 wire fixture. No producer, executable or physics ran.

Wire keys/types are copied from exact PR32 020437fa validator and exporter.
Dummy provenance deliberately identifies synthetic data; producer_emitted is the
required wire declaration, not execution evidence. Frames use existing synthetic
v1 numerical fixture. Never substitute this fixture for the missing actual packet.
"""
import copy
import hashlib
import json
from fixtures.rheon_source_derived import synthetic_frames, synthetic_manifest
import rheon_controls_contract as v2


def fixture():
    frames=synthetic_frames()
    raw=b''.join((json.dumps(f,separators=(',',':'))+'\n').encode() for f in frames)
    manifest=synthetic_manifest(raw);manifest['version']=2
    manifest['provenance']['source_sha256']['tools/import_dense3d_controls.py']='4'*64
    controls={'schema':v2.CONTROLS_SCHEMA,'version':2,
        'run_binding':{k:copy.deepcopy(manifest[k]) for k in v2.BINDING_KEYS},
        'frames_sha256':manifest['frames_sha256'],'axis_order':['x','y','z'],'side_order':['low','high'],
        'speed_sign':'positive outward normal','units':copy.deepcopy(v2.CONTROL_UNITS),
        'provenance':{'origin':'producer_emitted','author':'Explicitly synthetic source-derived fixture',
                      'source_note':'No producer execution, source or executable authenticity claimed'},'intervals':[]}
    for i in range(1,9):
        before,after=frames[i-1:i+1]
        controls['intervals'].append({'start_frame':i-1,'end_frame':i,'start_time_s':before['time_s'],
            'end_time_s':after['time_s'],'dt_s':after['dt_s'],'carrier_before':before['carrier_stamp'],
            'carrier_after':after['carrier_stamp'],'liquid_before':before['liquid_stamp'],'liquid_after':after['liquid_stamp'],
            'boundary_stamp':{'id':'47','version':'0'},'inlet_stamp':{'id':'53','version':'0'},
            'outward_speed_m_s':[[-.25,.25],[0,0],[0,0]],'inlet_fraction':[[0,0],[0,0],[0,0]],
            'source_mode':'none','source_rate_m3_s':0,'body_acceleration_m_s2':[0,0,0]})
    return pack(manifest,raw,controls)


def pack(manifest,frames,controls):
    manifest=copy.deepcopy(manifest)
    controls=json.dumps(controls,separators=(',',':'),allow_nan=True).encode()+b'\n' if type(controls) is dict else controls
    manifest.update(controls_file='controls.json',controls_bytes=len(controls),controls_sha256=hashlib.sha256(controls).hexdigest())
    return json.dumps(manifest,separators=(',',':')).encode()+b'\n',frames,controls
