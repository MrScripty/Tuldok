"""Package an explicitly source-bound binary mesh for Workbench acquisition."""
import argparse
import io
import os
from pathlib import Path
import sys
import tempfile
import zipfile

import binary_mesh_core as core


def read(path,cap):
    with Path(path).open('rb') as stream:raw=stream.read(cap+1)
    core.require(0<len(raw)<=cap,'source file exceeds bounded packet profile')
    return raw


def kenoma_packet(request_raw,response_raw,producer_raw):
    response=core.strict_json(response_raw,core.RESPONSE_BYTES)
    mesh=response.get('mesh',{})
    core.require(type(mesh.get('positions')) is list and type(mesh.get('normals')) is list
        and len(mesh['positions'])==len(mesh['normals'])<=core.VERTICES,'bounded source vertex arrays required')
    core.require(type(mesh.get('indices')) is list and 0<len(mesh['indices'])<=core.TRIANGLES*3
        and len(mesh['indices'])%3==0,'bounded source triangles required')
    class Vertices:
        def __len__(self):return len(mesh['positions'])
        def __iter__(self):
            for p,n in zip(mesh['positions'],mesh['normals']):
                core.require(type(p) is list and len(p)==3 and type(n) is list and len(n)==3,'source vector shape')
                yield [core.f32(x) for x in p+n]
    class Faces:
        def __len__(self):return len(mesh['indices'])//3
        def __iter__(self):
            for index in range(0,len(mesh['indices']),3):
                row=mesh['indices'][index:index+3]
                for value in row:core.integer(value,0,len(mesh['positions'])-1,'source index')
                yield row
    binary=core.binary_from_rows([{'name':x,'dtype':'float'} for x in core.PROPERTIES[1]],Vertices(),Faces(),'uint',
        ['tuldok_source_response_sha256 '+core.sha(response_raw),'tuldok_source_commit '+core.SOURCE_COMMIT])
    files={'request.json':request_raw,'response.json':response_raw,'producer.json':producer_raw}
    base={'units':'m','coordinate_system':{'frame':'character-local','handedness':'right','up_axis':'y'},
        'provenance':{'source':core.SOURCE_REPOSITORY,'revision':core.SOURCE_COMMIT,'license':'Apache-2.0; declared source license, local rights require review',
            'description':'Fresh deterministic artistic rig-bind response; original request/response and published producer manifest retained; no historical capture claim'}}
    return core.write_bundle(binary,files,'kenoma_rig_bind_v1',base)


def legacy_packet(source_raw,binary=None):
    import meshes
    with core.stored_zip(source_raw,['mesh.ply','mesh.json'],[meshes.PLY_LIMIT,meshes.MANIFEST_LIMIT]) as archive:
        prepared=meshes.prepare(archive.read('mesh.ply'),archive.read('mesh.json'))
    g=prepared['geometry'];m=prepared['metadata']['manifest']
    if binary is None:
        binary=core.binary_from_rows(g['properties'],g['vertices'],g['faces'],'int',
            ['tuldok_authoritative_source_bundle_sha256 '+core.sha(source_raw)])
    return core.write_bundle(binary,{'source.zip':source_raw},'tuldok_mesh_v1',
        {key:m[key] for key in ('units','coordinate_system','provenance')})


def main():
    if sys.platform != "linux":
        raise SystemExit("Bounded binary mesh packaging requires the qualified Linux resource worker.")
    import resource
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind',choices=['kenoma','legacy']);parser.add_argument('source',type=Path)
    parser.add_argument('output',type=Path);parser.add_argument('--binary',type=Path,help='Wrap existing native binary derivative; legacy source required')
    args=parser.parse_args()
    resource.setrlimit(resource.RLIMIT_AS,(core.WORKER_AS_BYTES,core.WORKER_AS_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU,(core.WORKER_CPU_SECONDS,core.WORKER_CPU_SECONDS))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    sources=[args.source/name for name in ('request.json','response.json','manifest.json')] if args.kind=='kenoma' else [args.source]
    if args.binary:sources.append(args.binary)
    core.require(all(args.output.absolute()!=p.absolute() and args.output.resolve()!=p.resolve()
        and not(args.output.exists() and p.exists() and os.path.samefile(args.output,p)) for p in sources),'output must not replace authoritative input')
    if args.kind=='kenoma':
        core.require(args.binary is None,'Kenoma packet derives binary from exact retained response')
        raw=kenoma_packet(read(args.source/'request.json',core.REQUEST_BYTES),read(args.source/'response.json',core.RESPONSE_BYTES),
            read(args.source/'manifest.json',core.MANIFEST_BYTES))
    else:raw=legacy_packet(read(args.source,2*1024*1024+32*1024+1024),read(args.binary,core.PLY_BYTES) if args.binary else None)
    result=core.validate_bundle(raw)
    fd,temporary=tempfile.mkstemp(prefix='.mesh-import-',dir=args.output.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,args.output)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
    print(core.encode({'profile':core.FORMAT,'bytes':len(raw),'sha256':core.sha(raw),'vertices':result['metadata']['vertex_count'],
        'triangles':result['metadata']['triangle_count'],'source':result['metadata']['manifest']['source']}))


if __name__=='__main__':main()
