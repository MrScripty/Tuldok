"""Independent retained-source/binary-wire/native whole-mesh consumer oracle.

QA-only shared legacy graph/ZIP/ASCII oracles precede production validation.
Kenoma evidence is fresh deterministic WASM regeneration, never historical capture.
No producer execution, physics, training, inference or compilation occurs here.
"""
import argparse
import base64
import copy
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests/fixtures'))
import check_native_mesh_consumer as qa
require=qa.require;sha=qa.sha;encoded=qa.encoded;decode=qa.decode
MAX_RELEASE=64*1024*1024;MAX_BUNDLE=12*1024*1024;MAX_PLY=4*1024*1024
MAX_META=8*1024*1024;MAX_SOURCE_META=32*1024;MAX_HEADER=64*1024;MAX_NPZ=16*1024*1024
SOURCE_COMMIT='136f4947c7ef9bd2d4fe5cff09086489b0cb501d'
SOURCE_REPOSITORY='https://github.com/MrScripty/Kenoma'
WASM_SHA='da3958056caeda3d190dfff7cb708657fb81c8389f953ad4c022a26e64bcdf8f'
DTYPES={'float':'<f4','double':'<f8','int':'<i4','uint':'<u4'}
SPLITS=qa.SPLITS
# Exact pinned samples.rs rest constructor, independently retained in the contract.
REST=[(0,.95,0,.16),(0,1.35,0,.21),(0,1.55,0,.07),(0,1.72,0,.13),
    (.32,1.4,0,.085),(.58,1.2,0,.065),(.79,1,0,.055),(-.32,1.4,0,.085),(-.58,1.2,0,.065),(-.79,1,0,.055),
    (.15,.85,0,.10),(.15,.48,0,.075),(.15,.08,.08,.065),(-.15,.85,0,.10),(-.15,.48,0,.075),(-.15,.08,.08,.065)]
LINKS=[(0,1),(1,2),(2,3),(1,4),(4,5),(5,6),(1,7),(7,8),(8,9),(0,10),(10,11),(11,12),(0,13),(13,14),(14,15)]


def identity(path):
    raw=qa.capture(path,MAX_RELEASE);return dict(path=str(path),bytes=len(raw),sha256=sha(raw))


def exact_f32(number):
    require(type(number) in (int,float,Decimal),'Exact source number primitive')
    token=str(number) if type(number)is Decimal else repr(number)
    value=float(number);exact=Fraction(Decimal(token).copy_abs())
    require(math.isfinite(value) and abs(value)<=1e12 and (value!=0 or not exact),'Finite source magnitude and no nonzero underflow')
    near=struct.unpack('<I',struct.pack('<f',abs(value)))[0]
    def real(bits):return struct.unpack('<f',struct.pack('<I',bits))[0]
    bits=min(range(max(0,near-1),near+2),key=lambda b:(abs(exact-Fraction.from_float(real(b))),b%2))
    require(not exact or real(bits)!=0,'No nonzero source f32 underflow')
    if token.startswith('-'):bits|=0x80000000
    wire=struct.pack('<I',bits);return struct.unpack('<f',wire)[0],wire


def effective_cell_size(operation):
    # Keep the original JSON decimal through the one native f32 conversion.
    token=operation.get('surface_options',{}).get('cell_size',Decimal('0.016'))
    cell=exact_f32(token)[0]
    require(exact_f32(Decimal('0.008'))[0]<=cell<=exact_f32(Decimal('0.04'))[0],'Bounded effective native cell size')
    factor=Fraction.from_float(exact_f32(Decimal('0.7'))[0])
    for _,_,_,radius in REST:
        product=Fraction.from_float(exact_f32(radius)[0])*factor
        with localcontext() as context:
            context.prec=200
            threshold=exact_f32(Decimal(product.numerator)/Decimal(product.denominator))[0]
        require(cell<=threshold,'Pinned native per-node radius resolution')
    return cell


def binary_oracle(raw,np):
    require(0<len(raw)<=MAX_PLY,'Whole binary PLY byte cap')
    stream=io.BytesIO(raw);head=[]
    while True:
        line=stream.readline(MAX_HEADER+1)
        require(line and line.endswith(b'\n') and stream.tell()<=MAX_HEADER and b'\r' not in line.replace(b'\r\n',b'') and not any(b<32 and b not in (9,10,13) for b in line),'Bounded complete binary ASCII header')
        text=line.decode('ascii').rstrip('\r\n')
        if text=='end_header':break
        head.append(text)
    require(head[:2]==['ply','format binary_little_endian 1.0'],'Exact supported binary version/order')
    grammar=[l.split() for l in head[2:] if not l.startswith('comment ')]
    require(grammar and len(grammar[0])==3 and grammar[0][:2]==['element','vertex'] and qa.INTEGER.fullmatch(grammar[0][2]),'Closed vertex element')
    n=int(grammar[0][2]);require(1<=n<=50000,'Whole vertex cap');props=[];cursor=1
    while cursor<len(grammar) and grammar[cursor][:1]==['property']:
        p=grammar[cursor];require(len(p)==3 and p[1] in ('float','double'),'Separate native scalar fields')
        props.append(dict(name=p[2],dtype=p[1]));cursor+=1
    require([p['name'] for p in props] in (['x','y','z'],['x','y','z','nx','ny','nz']),'Exact XYZ/normal axes')
    require(cursor<len(grammar) and len(grammar[cursor])==3 and grammar[cursor][:2]==['element','face'] and qa.INTEGER.fullmatch(grammar[cursor][2]),'Closed face element')
    t=int(grammar[cursor][2]);require(1<=t<=100000 and len(grammar)==cursor+2,'Whole triangle count cap')
    face=grammar[-1];require(face in (['property','list','uchar','int','vertex_indices'],['property','list','uchar','uint','vertex_indices']),'Ordered uchar int/uint triangle profile')
    face_type=face[3];offset=stream.tell();vtype=np.dtype([(p['name'],DTYPES[p['dtype']]) for p in props]);ftype=np.dtype([('count','u1'),('indices',DTYPES[face_type],(3,))])
    require(len(raw)==offset+n*vtype.itemsize+t*ftype.itemsize,'Exact whole native binary body association')
    vertices=np.frombuffer(raw,dtype=vtype,count=n,offset=offset);faces=np.frombuffer(raw,dtype=ftype,count=t,offset=offset+n*vtype.itemsize)
    columns={p['name']:vertices[p['name']].copy() for p in props};triangles=faces['indices'].copy();columns['vertex_indices']=triangles
    require(np.all(faces['count']==3) and np.all(triangles>=0) and np.all(triangles<n),'Native triangle list length and bounded indices')
    require(np.all(triangles[:,0]!=triangles[:,1]) and np.all(triangles[:,1]!=triangles[:,2]) and np.all(triangles[:,0]!=triangles[:,2]),'Distinct triangle corners')
    for a in columns.values():require(a.dtype.kind in 'fui' and np.all(np.isfinite(a)) and (a.dtype.kind!='f' or np.all(np.abs(a)<=1e12)),'Finite native fields')
    keys=np.sort(triangles,axis=1);require(len(np.unique(keys,axis=0))==t,'No duplicate unordered whole-mesh triangles')
    xyz=np.stack([columns[k] for k in ('x','y','z')],axis=1).astype('<f8')
    u=xyz[triangles[:,1]]-xyz[triangles[:,0]];v=xyz[triangles[:,2]]-xyz[triangles[:,0]]
    require(np.all(np.any(np.cross(u,v)!=0,axis=1)),'Nonzero representable cross product for every triangle')
    bounds=dict(min=[float(columns[k].min()) for k in ('x','y','z')],max=[float(columns[k].max()) for k in ('x','y','z')])
    # Reconstruct existing family JSON independently; native zero canonicalization is family-only.
    normalized=[[0.0 if value==0 else float(value) for value in vertex] for vertex in xyz]
    return dict(properties=props,columns=columns,vertex_count=n,triangle_count=t,face_type=face_type,bounds=bounds,
        vertices=normalized,faces=triangles.tolist(),header_bytes=offset,raw_sha256=sha(raw))


def source_oracle(files,np):
    require('mesh.ply' in files and 'mesh.json' in files and len(files['mesh.json'])<=MAX_SOURCE_META,'Binary manifest before source read')
    m=decode(files['mesh.json']);require(type(m)is dict and set(m)=={'format','geometry_file','geometry_bytes','geometry_sha256','units','coordinate_system','provenance','source'},'Closed source-bound manifest')
    require(m['format']=='tuldok_mesh_binary_v1' and m['geometry_file']=='mesh.ply' and type(m['geometry_bytes'])is int and m['geometry_bytes']==len(files['mesh.ply']) and m['geometry_sha256']==sha(files['mesh.ply']),'Exact retained binary descriptor')
    frame=m['coordinate_system'];require(m['units'] in ('m','cm','mm') and type(frame)is dict and set(frame)=={'frame','handedness','up_axis'} and frame['handedness'] in ('left','right') and frame['up_axis'] in ('x','y','z') and type(frame['frame'])is str and 0<len(frame['frame'])<=120,'Source units/frame')
    require(type(m['provenance'])is dict and set(m['provenance'])=={'source','revision','license','description'} and all(type(v)is str and v.strip() and len(v)<=1000 for v in m['provenance'].values()),'Original source provenance')
    source=m['source'];require(type(source)is dict and set(source)=={'kind','files'},'Closed source binding')
    names=['source.zip'] if source['kind']=='tuldok_mesh_v1' else ['request.json','response.json','producer.json']
    require(source['kind'] in ('tuldok_mesh_v1','kenoma_rig_bind_v1') and list(files)==['mesh.ply','mesh.json']+names and set(source['files'])==set(names),'Exact ordered source members/kind')
    caps={'source.zip':2*1024*1024+32*1024+1024,'request.json':32768,'response.json':8*1024*1024,'producer.json':32768}
    for name in names:
        desc=source['files'][name];require(type(desc)is dict and set(desc)=={'bytes','sha256'} and type(desc['bytes'])is int and 0<len(files[name])<=caps[name] and desc['bytes']==len(files[name]) and desc['sha256']==sha(files[name]),'Original source hash/byte association: '+name)
    g=binary_oracle(files['mesh.ply'],np);groups=[]
    if source['kind']=='tuldok_mesh_v1':
        pair=qa.zip_payloads(files['source.zip'],2,caps['source.zip']);require(list(pair)==['mesh.ply','mesh.json'],'Exact original legacy ASCII pair')
        original=qa.raw_pair_oracle(pair['mesh.ply'],pair['mesh.json']);old=original['metadata']['manifest']
        require(g['properties']==original['properties'] and g['face_type']=='int' and g['faces']==original['faces'],'Original native layout and triangle winding/order')
        for name,wire in original['columns'].items():require(g['columns'][name].tobytes()==wire,'Exact original source native bits: '+name)
        require(all(encoded(m[k])==encoded(old[k]) for k in ('units','coordinate_system','provenance')),'Original legacy units/frame/provenance retained')
        groups+=original['metadata']['protected_groups'];evidence=dict(kind='tuldok_mesh_v1',original_manifest=old,native_zero='existing source decoder canonical positive zero')
    else:
        request=decode(files['request.json']);response=decode(files['response.json']);producer=decode(files['producer.json'])
        exact=json.loads(files['response.json'].decode(),parse_float=Decimal)
        require(set(request)=={'version','operation'} and type(request['version'])is int and request['version']==1,'Closed actual bind request')
        op=request['operation'];require(type(op)is dict and set(op) in ({'type','rig_version'},{'type','rig_version','surface_options'}) and op['type']=='rig_bind' and type(op['rig_version'])is int and op['rig_version']==1,'Neutral supported bind operation')
        if 'surface_options' in op:
            require(type(op['surface_options'])is dict and set(op['surface_options'])=={'cell_size'},'Closed bind surface options')
        request_exact=json.loads(files['request.json'].decode(),parse_float=Decimal)
        cell=effective_cell_size(request_exact['operation'])
        require(set(response)=={'version','ok','rig_version','rig_id','graph','head','options','mesh'} and response['ok'] is True and type(response['version'])is int and response['version']==1 and type(response['rig_version'])is int and response['rig_version']==1 and type(response['rig_id'])is int and 1<=response['rig_id']<=2**32-1,'Closed neutral success response/transient rig id')
        require(set(response['head'])=={'yaw','pitch'} and all(type(v) in (int,float) and v==0 for v in response['head'].values()) and encoded(response['options'])==encoded(dict(ring_sides=8,target_segment_length_factor=1.25,max_edge_segments=64)),'Neutral head and exact legacy options')
        graph=response['graph'];require(set(graph)=={'nodes','edges'} and len(graph['nodes'])==16 and graph['edges']==[dict(a=a,b=b) for a,b in LINKS]
            and all(set(e)=={'a','b'} and type(e['a'])is type(e['b'])is int for e in graph['edges']),'Canonical typed rest graph associations')
        rest=dict(nodes=[dict(position=[exact_f32(x)[0] for x in (x,y,z)],radii=[exact_f32(r)[0]]*2,root=i==0) for i,(x,y,z,r) in enumerate(REST)],edges=graph['edges'])
        normalized=[]
        for node in exact['graph']['nodes']:
            require(set(node)=={'position','radii','root'} and len(node['position'])==3 and len(node['radii'])==2 and type(node['root'])is bool,'Complete node shape')
            normalized.append(dict(position=[exact_f32(v)[0] for v in node['position']],radii=[exact_f32(v)[0] for v in node['radii']],root=node['root']))
        require(normalized==rest['nodes'],'Exact pinned rest graph native values')
        for node,expected_node in zip(exact['graph']['nodes'],rest['nodes']):
            require(all(exact_f32(a)[1]==struct.pack('<f',b) for a,b in zip(node['position']+node['radii'],expected_node['position']+expected_node['radii'])),'Pinned rest graph IEEE bits including zero signs')
        mesh=response['mesh'];require(set(mesh)=={'positions','normals','indices','source_nodes','source_edges','diagnostics'} and g['properties']==[dict(name=k,dtype='float') for k in ('x','y','z','nx','ny','nz')] and g['face_type']=='uint','Kenoma native f32/u32 source schema')
        for name,axes in [('positions',('x','y','z')),('normals',('nx','ny','nz'))]:
            rows=exact['mesh'][name];require(type(rows)is list and len(rows)==g['vertex_count'] and all(type(row)is list and len(row)==3 for row in rows),'Complete source native XYZ arrays')
            for index,axis in enumerate(axes):
                wire=b''.join(exact_f32(row[index])[1] for row in rows);require(wire==g['columns'][axis].tobytes(),'Direct exact source decimal/native f32 bits: '+axis)
        indices=mesh['indices'];require(type(indices)is list and len(indices)==g['triangle_count']*3 and all(type(i)is int and 0<=i<g['vertex_count'] for i in indices),'Complete ordered u32 source indices')
        require(np.asarray(indices,dtype='<u4').tobytes()==g['columns']['vertex_indices'].tobytes(),'Exact native unsigned topology bits/order')
        for name,maximum in [('source_nodes',15),('source_edges',14)]:
            values=mesh[name];require(type(values)is list and len(values)==g['vertex_count'] and all(v is None or type(v)is int and 0<=v<=maximum for v in values),'Full sparse source association arrays')
        require(mesh['diagnostics']==[] and m['units']=='m' and frame==dict(frame='character-local',handedness='right',up_axis='y'),'Neutral diagnostics and declared model frame')
        require(set(producer)=={'fixture_version','provenance','source_commit','compatible_editor_checkpoint','protocol_version','rig_version','crate_version','wasm','coordinate_frame','request','response','counts','bounds','options','note'}
            and all(type(producer[k])is int and producer[k]==1 for k in ('fixture_version','protocol_version','rig_version'))
            and producer['source_commit']==SOURCE_COMMIT and producer['crate_version']=='0.1.0' and set(producer['wasm'])=={'bytes','sha256'}
            and type(producer['wasm']['bytes'])is int and producer['wasm']['sha256']==WASM_SHA and producer['wasm']['bytes']==471190,'Actual closed pinned producer source/artifact claim')
        for name in ('request','response'):
            p=producer[name];require(p['file']==name+'.json' and p['bytes']==len(files[name+'.json']) and p['sha256']==sha(files[name+'.json']),'Complete published producer descriptor')
        require(type(producer.get('provenance'))is str and 'Fresh deterministic' in producer['provenance'] and 'not a retained original' in producer['provenance'],'Truthful fresh regeneration provenance')
        require(producer['coordinate_frame']==dict(handedness='right-handed',up='+Y',head_forward='+Z',length_unit='metre',angle_unit='radian',space='character-local; no scene placement transform',triangle_winding='counterclockwise viewed from outside'),'Complete declared producer coordinate frame')
        counts=dict(source_nodes=16,source_edges=15,positions=g['vertex_count'],normals=g['vertex_count'],triangle_indices=g['triangle_count']*3,triangles=g['triangle_count'])
        require(set(producer['counts'])==set(counts) and all(type(producer['counts'][k])is int and producer['counts'][k]==v for k,v in counts.items()),'Complete producer counts associate to actual whole mesh')
        require(set(producer['bounds'])=={'min','max'},'Complete producer bounds')
        producer_exact=json.loads(files['producer.json'].decode(),parse_float=Decimal)
        for key in ('min','max'):
            require(type(producer_exact['bounds'][key])is list and len(producer_exact['bounds'][key])==3
                and b''.join(exact_f32(v)[1] for v in producer_exact['bounds'][key])==struct.pack('<3f',*g['bounds'][key]),'Producer bounds exact native bits')
        require(set(producer['options'])=={'cell_size','head'} and exact_f32(producer_exact['options']['cell_size'])[1]==exact_f32(cell)[1]
            and type(producer['options']['head'])is dict and set(producer['options']['head'])=={'yaw','pitch'}
            and all(type(v) in (int,float) and v==0 for v in producer['options']['head'].values())
            and producer['options']['head']==response['head'],'Complete producer binding option/native association')
        require(m['provenance']['source']==SOURCE_REPOSITORY and m['provenance']['revision']==SOURCE_COMMIT,'Exact declared producer pin')
        binding=dict(source_commit=SOURCE_COMMIT,rig_version=1,cell_size=exact_f32(cell)[0],rest_graph=rest)
        groups+=['kenoma-binding:'+sha(encoded(binding).encode())]
        evidence=dict(kind='kenoma_rig_bind_v1',binding=binding,producer=producer,transport_claims='Retained compressed-file and generation claims; consumer verifies exact uncompressed request/response and pinned WASM declaration, not generation authenticity.',transient_rig_id=response['rig_id'],head=response['head'],options=response['options'],
            sparse_associations=dict(source_nodes=g['vertex_count'],source_edges=g['vertex_count']),native_zero='binary source IEEE signed-zero bits retained; family alone canonicalizes zero')
        g['source_detail']=dict(request=request,head=response['head'],options=response['options'],graph=graph,sparse_associations={k:mesh[k] for k in ('source_nodes','source_edges')},diagnostics=mesh['diagnostics'],producer=producer)
    family=sha(encoded(dict(vertices=g['vertices'],faces=g['faces'],units=m['units'],coordinate_system=frame)).encode())
    groups=list(dict.fromkeys(groups+['mesh-source:'+sha(files['mesh.ply']),'mesh-family:'+family]))
    meta=dict(manifest=m,manifest_sha256=sha(files['mesh.json']),properties=g['properties'],vertex_count=g['vertex_count'],triangle_count=g['triangle_count'],bounds=g['bounds'],provided_normals=len(g['properties'])==6,
        protected_groups=groups,topology_dtype=DTYPES[g['face_type']],source_evidence=evidence,resource_profile='tuldok_mesh_binary_v1',scope='whole static mesh; exact source-bound geometry transport and inspection; no physics or training qualification')
    g['metadata']=meta;return g


def inspect_release(raw,np,expected=None):
    files=qa.zip_payloads(raw);require('manifest.json' in files and len(files['manifest.json'])<=MAX_META,'Bounded complete canonical manifest')
    m=decode(files['manifest.json']);require(type(m)is dict and set(m)=={'schema_version','seed','split_report','coordinate_contract','limitations','records','protected_components','vocabulary'},'Closed full-proof canonical manifest')
    require(type(m['schema_version'])is int and m['schema_version']==1 and type(m['seed'])is int and 0<=m['seed']<=2**32-1 and m['vocabulary']==[],'Canonical version/seed/no inferred labels')
    rows=m['records'];require(type(rows)is list and 1<=len(rows)<=64 and all(type(r)is dict and set(r)==qa.ROW_KEYS for r in rows),'Closed whole binary mesh rows')
    ids=[r['id'] for r in rows];require(len(set(ids))==len(ids) and all(type(i)is str and qa.ID.fullmatch(i) for i in ids),'Unique owner IDs')
    if expected is not None:
        require(type(expected)is list and len(expected)==len(rows),'Complete expected source snapshots');byid={r['id']:r for r in expected};require(set(byid)==set(ids),'Expected source IDs')
        for row in rows:
            original=byid[row['id']];require(set(original) in (qa.ROW_KEYS,qa.ROW_KEYS-{'asset','asset_sha256','split','export_group'}) and encoded(original)==encoded({k:row[k] for k in original}),'Exact complete original owner rows')
    require(set(files)=={'manifest.json','README.txt'}|{s+'/'+n for s in SPLITS for n in ('records.jsonl','coco.json')}|{'assets/'+i+'.zip' for i in ids},'Exact canonical whole binary mesh closure')
    bundles={};oracles={};total=0
    for row in rows:
        require(row['kind']=='mesh' and row['task']=='mesh_geometry' and row['review']=='human_reviewed' and row['source_available'] is row['source_lineage_known'] is True and row['source_split']=='unassigned','Available human-reviewed whole mesh source')
        qa.integer(row['revision'],'Record revision');require(type(row['source_revision'])is int and row['source_revision']==1,'Immutable source revision')
        require(all(row[k] is None for k in ('text','pixel_hash','book_id','session_id','width','height','corner_annotation')),'Mesh source identity')
        qa.strings(row['groups'],'Groups');qa.strings(row['parents'],'Parents',True)
        require(type(row['annotation'])is dict and set(row['annotation'])=={'note'} and type(row['annotation']['note'])is str and 0<len(row['annotation']['note'])<=4000 and row['annotation']['note'].strip(),'Human inspection note')
        require(row['split'] in SPLITS and type(row['provenance'])is dict and type(row['provenance'].get('rights'))is str,'Retained split/rights claims')
        name='assets/'+row['id']+'.zip';bundle=files[name];total+=len(bundle)
        require(row['asset']==name and 0<len(bundle)<=MAX_BUNDLE and total<=40*1024*1024 and sha(bundle)==row['content_hash']==row['source_sha256']==row['asset_sha256'],'Complete immutable source hash/size associations')
        rawfiles=qa.zip_payloads(bundle,5,MAX_BUNDLE);oracle=source_oracle(rawfiles,np)
        require(encoded(row['mesh'])==encoded(dict(oracle['metadata'],bundle_bytes=len(bundle))) and set(oracle['metadata']['protected_groups'])<=set(row['groups']),'Independently reconstructed source metadata/native families')
        bundles[row['id']]=rawfiles;oracles[row['id']]=oracle
    for split in SPLITS:
        rawstream=files[split+'/records.jsonl'];require(len(rawstream)<=MAX_META and (not rawstream or rawstream.endswith(b'\n')),'Complete bounded split stream')
        lines=rawstream.splitlines();require(len(lines)<=64 and all(0<len(l)<=256*1024 for l in lines),'Bounded metadata lines')
        require(encoded([decode(l) for l in lines])==encoded([r for r in rows if r['split']==split]),'Exact split/source projection')
        coco=decode(files[split+'/coco.json']);require(len(files[split+'/coco.json'])<=4096 and set(coco)=={'info','licenses','images','annotations','categories'} and all(coco[k]==[] for k in ('licenses','images','annotations','categories')),'No mesh conversion to COCO/image targets')
    proof=dict(m,assignments={r['id']:r['split'] for r in rows});family,context=qa.graph_oracle(proof,rows);qa.allocation_oracle(proof,family)
    require(all(r['export_group']==family[r['id']] for r in rows),'Whole declared family export group')
    return dict(manifest=m,payloads=files,bundles=bundles,oracles=oracles,context=context)


def verify_fields(fields,oracle,np):
    require(type(fields)is dict and list(fields)==[p['name'] for p in oracle['properties']]+['vertex_indices'],'Separate original native axes/topology')
    result=[]
    for name,expected in oracle['columns'].items():
        observed=fields[name];require(isinstance(observed,np.ndarray) and observed.dtype.str==expected.dtype.str and observed.shape==expected.shape and observed.tobytes()==expected.tobytes(),'Exact source native dtype/shape/order/bits: '+name)
        result.append(dict(name=name,dtype=observed.dtype.str,shape=list(observed.shape),native_sha256=sha(observed.tobytes()),native_hex=observed.tobytes().hex() if observed.size<=32 else None,values=observed.tolist() if observed.size<=32 else None))
    return result


def actual_read(path,oracle,np,plyfile):
    with path.open('rb') as source:actual=plyfile.PlyData.read(source,mmap=False)
    require(not actual.text and actual.byte_order=='<' and [e.name for e in actual.elements]==['vertex','face'],'Actual released binary reader format/elements/order')
    vertex=actual['vertex'].data;require(vertex.dtype.names==tuple(p['name'] for p in oracle['properties']),'Actual native property order')
    face=actual['face'];require(face.data.dtype.names==('vertex_indices',) and len(face.data)==oracle['triangle_count'] and face.properties[0].len_dtype=='u1' and face.properties[0].val_dtype==('i4' if oracle['face_type']=='int' else 'u4'),'Actual int/uint topology retention')
    require(all(row.shape==(3,) and row.dtype.str==DTYPES[oracle['face_type']] for row in face.data['vertex_indices']),'Actual ordered triangular list shape/dtype')
    fields={name:vertex[name] for name in vertex.dtype.names};fields['vertex_indices']=np.stack(face.data['vertex_indices'])
    return actual,dict(status='PASS',file=identity(path),attributes=verify_fields(fields,oracle,np))


def exercise(path,out,np,plyfile,expected=None):
    from native_binary_mesh_dataset import NativeBinaryMeshDataset
    raw=qa.capture(path,MAX_RELEASE);checked=inspect_release(raw,np,expected);rows=checked['manifest']['records'];out.mkdir(parents=True,exist_ok=True)
    captured=out/'captured-release.zip';captured.write_bytes(raw);samples=[]
    context=[s for key in sorted(checked['manifest']['protected_components']) for s in checked['manifest']['protected_components'][key]]
    for split in SPLITS:
        selected=[r for r in rows if r['split']==split]
        if not selected:continue  # Existing unit tests exercise empty-split refusal.
        dataset=NativeBinaryMeshDataset(captured,sha256=sha(raw),split=split);require(len(dataset)==len(selected),'One complete mesh per frozen family sample')
        for index,row in enumerate(selected):
            oracle=checked['oracles'][row['id']];sample=dataset[index];require(set(sample)=={'fields','metadata'},'Closed native sample')
            attrs=verify_fields(sample['fields'],oracle,np);meta=sample['metadata']
            require(set(meta)=={'schema','release_sha256','split','array_axes','properties','record','declared_family_context','units','coordinate_system','attribute_semantics','derivation','consumer','limitations','source_evidence'},'Complete closed binary source sample metadata')
            require(meta['schema']=='native_binary_mesh_sample_v1' and meta['release_sha256']==sha(raw) and meta['split']==split and encoded(meta['record'])==encoded(row),'Exact complete immutable owner metadata')
            require(meta['array_axes']==dict(vertex_properties=['vertex'],vertex_indices=['triangle','corner']) and meta['properties']==[{k:a[k] for k in ('name','shape','dtype')} for a in attrs],'Native axes/dtypes and whole topology')
            require(encoded(meta['declared_family_context'])==encoded(context) and encoded(meta['source_evidence'])==encoded(oracle['metadata']['source_evidence']) and meta['units']==row['mesh']['manifest']['units'] and encoded(meta['coordinate_system'])==encoded(row['mesh']['manifest']['coordinate_system']),'Full family, sparse/producer evidence and original source units/frame')
            require(meta['consumer']==dict(plyfile='1.1.3',plyfile_module_sha256=sha(Path(plyfile.__file__).read_bytes()),numpy='2.5.3'),'Actual installed released reader identity')
            binary=out/(split+'-'+str(index)+'.ply');binary.write_bytes(b'previous binary output');dataset.write_ply(binary,index=index)
            require(binary.read_bytes()==checked['bundles'][row['id']]['mesh.ply'],'Retained authoritative binary PLY byte exact')
            derivation=dict(representation='retained source-bound binary PLY; exact authoritative files remain in original bundle',format='binary_little_endian PLY1.0',sha256=sha(binary.read_bytes()),bytes=binary.stat().st_size,
                bundle_sha256=row['content_hash'],source=row['mesh']['manifest']['source'],zero_semantics=oracle['metadata']['source_evidence']['native_zero'],release_sha256=sha(raw),record_id=row['id'],revision=row['revision'],source_revision=row['source_revision'],split=split)
            require(encoded(meta['derivation'])==encoded(derivation),'Complete source-bound native binary identity and zero semantics')
            actual,reading=actual_read(binary,oracle,np,plyfile)
            written=out/(split+'-'+str(index)+'-external-roundtrip.ply');actual.write(str(written))
            written_oracle=binary_oracle(qa.capture(written,MAX_PLY),np);verify_fields(written_oracle['columns'],oracle,np)
            _,reread=actual_read(written,oracle,np,plyfile)
            npz=out/(split+'-'+str(index)+'.npz');npz.write_bytes(b'previous NPZ output');dataset.write_npz(npz,index=index);require(npz.stat().st_size<=MAX_NPZ,'Complete pickle-free NPZ cap')
            with np.load(npz,allow_pickle=False) as saved:
                require(set(saved.files)==set(sample['fields'])|{'metadata_utf8'},'Closed numeric-only and UTF8 NPZ keys')
                verify_fields({name:saved[name] for name in sample['fields']},oracle,np)
                require(saved['metadata_utf8'].dtype==np.dtype('uint8') and saved['metadata_utf8'].ndim==1 and encoded(decode(saved['metadata_utf8'].tobytes()))==encoded(meta),'Complete NPZ metadata UTF8')
            bundle=out/(split+'-'+str(index)+'-mesh-import.zip');bundle.write_bytes(b'previous import output');dataset.write_import_bundle(bundle,index=index)
            require(bundle.read_bytes()==checked['payloads'][row['asset']],'Complete importable output byte-exact including all authoritative source files')
            samples.append(dict(id=row['id'],split=split,index=index,attributes=attrs,npz=identity(npz),retained_ply=identity(binary),import_bundle=identity(bundle),actual_binary_read=reading,
                external_writer_roundtrip=identity(written),external_writer_reader=reread,metadata=meta,
                authoritative_files={name:dict(bytes=len(b),sha256=sha(b)) for name,b in checked['bundles'][row['id']].items()},source_detail=oracle.get('source_detail')))
    return dict(status='PASS',release=identity(path),records=len(rows),families=len(checked['manifest']['protected_components']),declared_context_members=len(context),samples=samples,actual_external_file_reads=2*len(samples),actual_external_file_writes=len(samples)),checked


def upload(workbench,raw,name):
    from binary_mesh_assets import UploadManager
    owner=UploadManager(workbench);chunks=[]
    try:
        start=owner.start(dict(bytes=len(raw),sha256=sha(raw),name=name));require(start['offset']==0 and start['chunk_bytes']==65536,'Bounded chunk protocol start')
        token=start['token']
        for offset in range(0,len(raw),65536):
            part=raw[offset:offset+65536];reply=owner.chunk(dict(token=token,offset=offset,data=base64.b64encode(part).decode()))
            require(reply['offset']==offset+len(part),'Strict chunk byte offset/sequence');chunks.append(dict(offset=offset,bytes=len(part)))
        row=owner.finish(dict(token=token));require(row['review']=='draft' and row['annotation'] is None and row['provenance']['rights']=='unknown' and row['source_split']=='unassigned','New owned unreviewed source/rights state')
        return row,dict(bytes=len(raw),sha256=sha(raw),chunks=chunks,chunk_bytes=65536)
    finally:owner.close()


def ref(row):return {k:row[k] for k in ('id','revision','source_revision')}


def review(w,row,status='human_reviewed'):
    return w.save(row['id'],dict(ref(row),task='mesh_geometry',groups=row['groups'],annotation={'note':'Authored whole binary mesh source/native transport QA; no physics or training qualification.'},review=status))


def freeze(dataset,rows,path):
    request=dict(items=[ref(r) for r in rows],ratios=dict(train=50,validation=50,test=0),seed=87)
    preview=dataset.releases.preview(request);require(preview['eligible'],'Human-reviewed whole-family release eligible')
    release=dataset.releases.create(dict(request,preview_token=preview['preview_token']));path.write_bytes(dataset.releases.locate(release['id']).read_bytes());return path


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--release',type=Path);p.add_argument('--expected-rows',type=Path);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();out=qa.output_preflight(args.output);np,plyfile,pins=qa.pins()
    from app import Dataset
    expected=decode(qa.capture(args.expected_rows,MAX_META)) if args.expected_rows else None
    if type(expected)is dict:expected=expected['records']
    intake=[]
    if args.release:path=args.release
    else:
        from binary_mesh_fixture import packets
        first=Dataset(str(out/'checker-owner-first'))
        try:
            rows=[]
            for name,raw in packets():
                # Independent complete-source oracle runs BEFORE production intake.
                source_oracle(qa.zip_payloads(raw,5,MAX_BUNDLE),np)
                row,proof=upload(first.workbench,raw,name);rows.append(review(first.workbench,row));intake.append(dict(name=name,upload=proof))
            path=freeze(first,rows,out/'checker-first-release.zip');expected=rows
        finally:first.close()
    first_report,checked=exercise(path,out/'first',np,plyfile,expected);original=qa.capture(path,MAX_RELEASE)
    second=Dataset(str(out/'checker-owner-second'));transfer=[]
    try:
        rows=[]
        for original_row in checked['manifest']['records']:
            exported=next(s['import_bundle'] for s in first_report['samples'] if s['id']==original_row['id'])
            exported_path=Path(exported['path']);require(identity(exported_path)==exported,'Actual published importable file custody')
            raw=qa.capture(exported_path,MAX_BUNDLE);require(raw==checked['payloads'][original_row['asset']],'Actual importable target equals complete original source bundle')
            row,proof=upload(second.workbench,raw,'Second owner '+original_row['name'])
            require(row['id'] not in {r['id'] for r in checked['manifest']['records']} and row['parents']==[] and encoded(row['mesh'])==encoded(original_row['mesh']),'New ID with complete exact source metadata, no inherited review/relationships')
            transfer.append(dict(original_id=original_row['id'],new_id=row['id'],imported_consumer_output=exported,admitted=copy.deepcopy(row),upload=proof));rows.append(row)
        request=dict(items=[ref(r) for r in rows],ratios=dict(train=50,validation=50,test=0),seed=87);require(not second.releases.preview(request)['eligible'],'Unreviewed second-owner bundles cannot freeze')
        rows=[review(second.workbench,r,'draft') for r in rows];rows=[second.workbench.get(r['id']) for r in rows]
        require(all(r['review']=='draft' for r in rows),'Saved/reopened local draft state')
        for t,r in zip(transfer,rows):t['reopened_draft']=copy.deepcopy(r)
        rows=[review(second.workbench,r) for r in rows]
        for t,r in zip(transfer,rows):t['reviewed']=copy.deepcopy(r)
        second_path=freeze(second,rows,out/'checker-second-release.zip');second_report,other=exercise(second_path,out/'second',np,plyfile,rows)
        for t in transfer:
            a=next(r for r in checked['manifest']['records'] if r['id']==t['original_id']);b=next(r for r in other['manifest']['records'] if r['id']==t['new_id'])
            require(checked['payloads'][a['asset']]==other['payloads'][b['asset']],'Complete raw authoritative bundle byte-exact across owners')
    finally:second.close()
    require(qa.capture(path,MAX_RELEASE)==original,'Original owner release unchanged')
    result=dict(status='PASS',scope='Whole source-bound binary mesh intake, retained native bits and actual file consumer/writer/NPZ/importable bundle transport; no physics, training or quality qualification.',
        role='Checker authored independently of root-owned binary parser/worker/consumer; independent stdlib exact Decimal/Fraction source numbers and NumPy wire layout/profile/topology/schema/graph QA oracles precede production.',
        packet_origin='actual_browser_or_supplied_owner_release' if args.release else 'checker_owned_local_source_fixture_upload',second_packet_origin='checker_created_complete_original_bundle_reimport',
        records=first_report['records'],release_sha256=sha(original),samples=first_report['samples'],first=first_report,second=second_report,pins=pins,intake=intake,transfer=transfer,
        actual_external_file_reads=first_report['actual_external_file_reads']+second_report['actual_external_file_reads'],
        fixture_provenance='Kenoma fixture is fresh deterministic rig_bind WASM regeneration at pinned source/artifact; not a retained historical request/response capture.',
        caveat='Complete raw bundles preserve all authoritative sources and binding/family groups; new owner gets unknown-rights drafts, new IDs and its own whole-family assignment, without sender review/rights/extra local relationships.',
        consumer_limits=dict(vertices=50000,triangles=100000,bundle_bytes=MAX_BUNDLE,ply_bytes=MAX_PLY,header_bytes=MAX_HEADER,response_bytes=8*1024*1024,release_bytes=MAX_RELEASE,selected_bytes=40*1024*1024,metadata_bytes=MAX_META,context_members=5000,npz_bytes=MAX_NPZ))
    (out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n');print('Native binary source-bound mesh actual reader/writer, NPZ and import-bundle roundtrip PASS: '+str(out))


if __name__=='__main__':main()
