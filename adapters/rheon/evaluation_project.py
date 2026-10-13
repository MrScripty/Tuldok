"""Assemble evaluation sources; inputs are selected from one completed training Run."""
import argparse
import os
from pathlib import Path
import shutil
import uuid

if __package__:
    from . import evaluate, cpu_compare, generate
else:
    import evaluate
    import cpu_compare
    import generate


def definition(sources,snapshot):
    evaluate.require(type(snapshot) is str and generate.HASH.fullmatch(snapshot),'Runtime snapshot SHA256 required.')
    native='lab/target/release/rheon-trajectory-parallel'
    arguments=[]
    for slot in evaluate.INPUTS:arguments.extend([{'literal':'--'+slot.replace('_','-')},{'input':slot}])
    for name,token in [('build-receipt',{'input':'build_receipt'}),('native-policy',{'native_policy':native}),
                       ('input-evidence',{'input_evidence':True}),('runtime-snapshot-sha256',{'literal':snapshot}),
                       ('output',{'output_dir':True})]:arguments.extend([{'literal':'--'+name},token])
    return {'schema_version':1,'format':'external_recipe_v1','id':'rheon-autonomous-evaluation',
            'name':'Rheon autonomous CPU evaluation','version':1,'runtime':'captured_cpu_python_v1',
            'runtime_snapshot_sha256':snapshot,'sources':[{'path':name,'sha256':generate.sha(raw)} for name,raw in sorted(sources.items())],
            'native_sources':[native],'entrypoint':'evaluate.py','arguments':arguments,'parameters':{},
            'inputs':{**{name:{'max_bytes':cap} for name,(_role,cap) in evaluate.INPUTS.items()},'build_receipt':{'max_bytes':1024*1024}},
            'outputs':[{'path':name,'role':role,'max_bytes':cap,'required':True} for name,role,cap in evaluate.outputs()],
            'environment':{},'resources':{'profile':'captured_cpu_large_outputs_v1','wall_seconds':2400,'max_output_bytes':evaluate.TOTAL_LIMIT}}


def assemble(lab_root,binary,build_receipt,runtime_snapshot_sha256,destination):
    lab=Path(lab_root);adapter=Path(__file__).parent
    native=generate.capture(binary,8*1024*1024)[0];build=generate.capture(build_receipt,1024*1024)[0]
    evaluate.require(generate.sha(native)==cpu_compare.BINARY_SHA256 and generate.sha(build)==cpu_compare.BUILD_RECEIPT_SHA256,
                     'Qualified parallel build required.')
    sources={'lab/target/release/rheon-trajectory-parallel':native}
    for name,digest in cpu_compare.SOURCES.items():
        raw=generate.capture(lab/'scripts'/name,65536)[0]
        evaluate.require(generate.sha(raw)==digest,'Original numerical source differs.')
        sources['lab/scripts/'+name]=raw
    for name in ('evaluate.py','cpu_compare.py','generate.py','native_transport.py'):
        sources[name]=generate.capture(adapter/name,256*1024)[0]
    recipe=generate.encode(definition(sources,runtime_snapshot_sha256))
    manifest={'schema_version':1,'id':uuid.uuid4().hex,'name':'Rheon autonomous CPU evaluation',
              'data':[{'id':'build_receipt','label':'Parallel build evidence','path':'build-receipt.json','sha256':generate.sha(build)}],
              'recipes':[{'id':'evaluate','label':'Evaluate completed training checkpoint','path':'recipe.json','sha256':generate.sha(recipe)}],
              'evidence':[],'requirements':[{'id':'completed-training','label':'Bind four verified artifacts from one completed training Run'}]}
    files={**sources,'build-receipt.json':build,'recipe.json':recipe,'project.json':generate.encode(manifest)}
    destination=Path(destination);destination.mkdir(mode=0o700,exist_ok=False)
    try:
        for name,raw in files.items():
            path=destination/name;path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as handle:
                handle.write(raw);handle.flush();os.fchmod(handle.fileno(),0o400);os.fsync(handle.fileno())
        for directory in [*sorted((p for p in destination.rglob('*') if p.is_dir()),reverse=True),destination]:
            fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
    except BaseException:
        shutil.rmtree(destination);raise
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('lab-root','binary','build-receipt','runtime-snapshot-sha256','destination'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    manifest=assemble(args.lab_root,args.binary,args.build_receipt,args.runtime_snapshot_sha256,args.destination)
    print(generate.encode({'project_id':manifest['id'],'manifest':str(Path(args.destination)/'project.json')}).decode())


if __name__=='__main__':main()
