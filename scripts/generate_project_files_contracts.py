"""Derive installed browser pins/routes from the local canonical API registry."""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import agent_api


def render(original):
    names=sorted(name for name in agent_api._CONTRACTS if name.startswith('project_files.'))
    tables={
        'CONTRACTS':{name:agent_api.contract(name,1)['sha256'] for name in names},
        'VERSIONS':{name:{str(v):agent_api.contract(name,v)['sha256'] for v in sorted(agent_api._CONTRACTS[name])}
                    for name in names if len(agent_api._CONTRACTS[name])>1},
        'ROUTES':{name:{'method':agent_api.operation(name)['method'],'path':agent_api.operation(name)['path'],
                        'mutation':agent_api.operation(name)['side_effects']}
                  for name in sorted(agent_api.PROJECT_FILES_M2|agent_api.PROJECT_FILES_M3|agent_api.PROJECT_FILES_M4)}}
    for label,value in tables.items():
        pattern=r'(/\* PROJECT_FILES_'+label+r'_START \*/\s*)(.*?)(\s*/\* PROJECT_FILES_'+label+r'_END \*/)'
        generated=json.dumps(value,sort_keys=True,indent=2)
        original,count=re.subn(pattern,lambda m:m[1]+generated+m[3],original,flags=re.S)
        if count!=1:raise ValueError('Exactly one installed '+label+' table required')
    return original


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true')
    args=parser.parse_args();path=ROOT/'static/project-files.js';original=path.read_text();expected=render(original)
    if args.check:
        if original!=expected:raise SystemExit('Installed project-file browser contracts are stale')
    elif original!=expected:path.write_text(expected)
