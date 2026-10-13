"""Assemble a frozen-release CPU training project; never fit during assembly."""
import argparse
import os
from pathlib import Path
import shutil
import uuid

if __package__:
    from . import cpu_train, cpu_compare, generate
else:
    import cpu_train
    import cpu_compare
    import generate

COLD_FILES = ('access.py','audio_assets.py','audio_classification_export.py','audio_export.py','bulk_import.py',
              'canonical_release.py','caption_import.py','dataset_releases.py','image_classification_export.py',
              'immutable_assets.py','meshes.py','native_text_import.py','recipe_process.py','scientific_fields.py',
              'scientific_release.py','text_classification_export.py','text_corpus_export.py','workbench.py')


def definition(sources, runtime_snapshot_sha256):
    cpu_train.require(type(runtime_snapshot_sha256) is str and generate.HASH.fullmatch(runtime_snapshot_sha256),
                      'A qualified runtime snapshot SHA256 is required.')
    native='lab/target/release/rheon-trajectory-parallel'
    arguments=[]
    for name in cpu_train.RELEASE_NAMES:arguments.extend([{'literal':'--release'},{'input':name}])
    for name,token in [('build-receipt',{'input':'build_receipt'}),('native-policy',{'native_policy':native}),
                       ('runtime-snapshot-sha256',{'literal':runtime_snapshot_sha256}),('threads',{'parameter':'threads'}),('output',{'output_dir':True})]:
        arguments.extend([{'literal':'--'+name},token])
    return {'schema_version':1,'format':'external_recipe_v1','id':'rheon-cpu-training',
            'name':'Rheon frozen-field CPU fit','version':1,'runtime':'captured_cpu_python_v1',
            'runtime_snapshot_sha256':runtime_snapshot_sha256,
            'sources':[{'path':name,'sha256':generate.sha(raw)} for name,raw in sorted(sources.items())],
            'native_sources':[native],'entrypoint':'cpu_train.py','arguments':arguments,
            'parameters':{'threads':{'type':'integer','min':1,'max':8,'default':8}},
            'inputs':{**{name:{'max_bytes':40*1024*1024} for name in cpu_train.RELEASE_NAMES},
                      'build_receipt':{'max_bytes':1024*1024}},
            'outputs':[{'path':name,'role':role,'max_bytes':cap,'required':True} for name,role,cap in cpu_train.OUTPUTS],
            'environment':{},'resources':{'wall_seconds':600,'max_output_bytes':64*1024*1024}}


def assemble(lab_root,binary,build_receipt,runtime_snapshot_sha256,destination):
    lab=Path(lab_root);adapter=Path(__file__).parent;repository=adapter.parents[1]
    native=generate.capture(binary,8*1024*1024)[0];build=generate.capture(build_receipt,1024*1024)[0]
    cpu_train.require(generate.sha(native)==cpu_compare.BINARY_SHA256
                      and generate.sha(build)==cpu_compare.BUILD_RECEIPT_SHA256,'Qualified parallel build required.')
    sources={'lab/target/release/rheon-trajectory-parallel':native}
    for name,digest in cpu_compare.SOURCES.items():
        raw=generate.capture(lab/'scripts'/name,65536)[0]
        cpu_train.require(generate.sha(raw)==digest,'Original lab algorithm changed.')
        sources['lab/scripts/'+name]=raw
    for name in ('cpu_train.py','cpu_compare.py','native_transport.py','generate.py'):
        sources[name]=generate.capture(adapter/name,256*1024)[0]
    for name in COLD_FILES:sources['cold/'+name]=generate.capture(repository/name,8*1024*1024)[0]
    recipe=generate.encode(definition(sources,runtime_snapshot_sha256))
    manifest={'schema_version':1,'id':uuid.uuid4().hex,'name':'Rheon frozen-field CPU training',
              'data':[{'id':'build_receipt','label':'Parallel build evidence','path':'build-receipt.json','sha256':generate.sha(build)}],
              'recipes':[{'id':'train','label':'Fit from six frozen training releases','path':'recipe.json','sha256':generate.sha(recipe)}],
              'evidence':[],'requirements':[{'id':'reviewed-training','label':'Bind six reviewed train-only releases containing all12 whole seed trajectories'}]}
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
