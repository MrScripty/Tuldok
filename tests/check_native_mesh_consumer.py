"""Independent canonical mesh/family/native/binary PLY/NPZ oracle; no models or training.

Archive and native-bit checks do not call the production dataset validator.
Only then is the actual reusable dataset and pinned file reader exercised.
"""
import argparse
import base64
import copy
from decimal import Decimal
from fractions import Fraction
import hashlib
import importlib.metadata
import io
import json
import math
from pathlib import Path
import re
import stat
import struct
import sys
import warnings
import zipfile

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=ROOT/'tests/fixtures'
MAX_PHYSICAL=64*1024*1024
MAX_LOGICAL=64*1024*1024
MAX_METADATA=8*1024*1024
MAX_RECORDS=64
MAX_MEMBERS=72
MAX_CONTEXT=5000
MAX_BUNDLES=40*1024*1024
MAX_NPZ=16*1024*1024
MAX_BINARY=4*1024*1024
MAX_BINARY_HEADER=64*1024
SPLITS=('train','validation','test')
ID=re.compile(r'[a-f0-9]{32}')
HASH=re.compile(r'[a-f0-9]{64}')
NUMBER=re.compile(r'^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$')
INTEGER=re.compile(r'^(?:0|[1-9][0-9]*)$')
SNAPSHOT_KEYS=set('id kind revision source_revision content_hash pixel_hash groups parents source_available source_lineage_known source_split source_sha256 book_id session_id'.split())
ROW_KEYS=SNAPSHOT_KEYS|set('annotation asset asset_sha256 corner_annotation created_at export_group height name mesh provenance review split task text updated_at width'.split())
DTYPES={'float':'<f4','double':'<f8'}


def require(condition, message):
    if not condition:
        raise ValueError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)

def decode(raw):
    require(type(raw) is bytes and len(raw) <= MAX_LOGICAL, 'JSON byte cap')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    def bad(value):
        raise ValueError('Nonfinite JSON ' + value)
    try:
        result = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=bad)
        pending = [(result, 0)]
        while pending:
            value, depth = pending.pop()
            require(depth <= 64, 'JSON depth cap')
            if type(value) is float:
                require(math.isfinite(value), 'Nonfinite JSON overflow')
            elif type(value) is dict:
                pending.extend((v, depth + 1) for v in value.values())
            elif type(value) is list:
                pending.extend((v, depth + 1) for v in value)
            elif type(value) is str:
                value.encode('utf-8')
        return result
    except (UnicodeError, RecursionError, OverflowError) as error:
        raise ValueError('Malformed bounded UTF-8 JSON') from error

def capture(path, maximum):
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    require(0 < len(raw) <= maximum, 'Captured file byte cap')
    return raw

def zip_payloads(raw, maximum_members=MAX_MEMBERS, logical_cap=MAX_LOGICAL):
    require(type(raw) is bytes and 22 <= len(raw) <= MAX_PHYSICAL, 'ZIP physical cap')
    require(raw[-22:-18] == b'PK\x05\x06', 'Exact comment-free ZIP EOF')
    _, disk, central_disk, disk_count, count, size, offset, comment = struct.unpack('<4s4H2IH', raw[-22:])
    require(disk == central_disk == comment == 0 and disk_count == count and 1 <= count <= maximum_members,
        'ZIP entry count before allocation')
    require(offset + size == len(raw) - 22, 'Exact ZIP central custody')
    cursor = offset
    for _ in range(count):
        require(cursor + 46 <= offset + size and raw[cursor:cursor + 4] == b'PK\x01\x02', 'ZIP central record')
        name, extra, note = struct.unpack_from('<3H', raw, cursor + 28)
        require(0 < name <= 256 and extra == note == 0, 'ZIP names/no ZIP64 or member comments')
        cursor += 46 + name
    require(cursor == offset + size, 'ZIP exact declared central count')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            require(len(infos) == count and len({i.filename for i in infos}) == count, 'Duplicate ZIP members')
            require(sum(i.file_size for i in infos) <= logical_cap, 'Complete logical ZIP cap')
            payloads = {}; cursor = 0
            for item in sorted(infos, key=lambda i: i.header_offset):
                require(item.compress_type == zipfile.ZIP_STORED and item.compress_size == item.file_size
                    and item.flag_bits in (0, 0x800), 'Only plain stored ZIP members')
                require(stat.S_IFMT(item.external_attr >> 16) in (0, stat.S_IFREG)
                    and not item.is_dir() and not item.external_attr & 0x10, 'Only regular ZIP files')
                require(item.header_offset == cursor and raw[cursor:cursor + 4] == b'PK\x03\x04', 'Contiguous ZIP local custody')
                flags, method = struct.unpack_from('<HH', raw, cursor + 6)
                crc, compressed, logical, name_len, extra_len = struct.unpack_from('<IIIHH', raw, cursor + 14)
                require(flags == item.flag_bits and method == 0 and extra_len == 0 and crc == item.CRC
                    and compressed == logical == item.file_size, 'ZIP local/central association')
                name = raw[cursor + 30:cursor + 30 + name_len].decode('utf-8' if flags & 0x800 else 'cp437')
                require(name == item.filename and not name.startswith('/') and '\\' not in name
                    and all(p not in ('', '.', '..') for p in name.split('/')), 'ZIP path association')
                cursor += 30 + name_len + logical
                require(cursor <= offset, 'ZIP payload custody')
                payloads[name] = archive.read(item)
            require(cursor == offset, 'No hidden ZIP prefix/trailer')
            return payloads
    except (zipfile.BadZipFile, UnicodeError, RuntimeError, OSError, EOFError, struct.error) as error:
        raise ValueError('Invalid ZIP bytes/CRC') from error

def integer(value, name):
    require(type(value) is int and 1 <= value <= 2**63 - 1, name + ' exact positive signed64 integer')

def strings(value, name, identifiers=False):
    require(type(value) is list and len(value) <= 30
        and all(type(v) is str and v and len(v) <= 120 and (not identifiers or ID.fullmatch(v)) for v in value)
        and len(value) == len(set(value)), name + ' bounded unique strings')

def archive_from(payloads, duplicate=None, symlink=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_STORED) as archive:
        for name, raw in payloads.items():
            info = zipfile.ZipInfo(name)
            if name == symlink: info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, raw)
        if duplicate:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                archive.writestr(duplicate, payloads[duplicate])
    return output.getvalue()

def output_preflight(path):
    output = path.resolve()
    try:
        relative = output.relative_to(ROOT.resolve())
        require(relative.parts and relative.parts[0] in ('build', 'output'), 'Output cannot write tracked source')
    except ValueError:
        require(not output.is_relative_to(ROOT.resolve()), 'Output cannot write tracked source')
    output.mkdir(parents=True, exist_ok=True)
    return output


def graph_oracle(manifest, rows):
    snapshots = manifest['protected_components']
    require(type(snapshots) is dict and 1 <= len(snapshots) <= MAX_CONTEXT, 'Bounded protected components')
    require(sum(len(v) for v in snapshots.values() if type(v) is list) <= MAX_CONTEXT, 'Total context cap')
    parents = {}; by_id = {}; family_by_id = {}
    def root(key):
        parents.setdefault(key, key)
        while key != parents[key]:
            parents[key] = parents[parents[key]]; key = parents[key]
        return key
    def join(a, b):
        parents[root(b)] = root(a)
    for family, members in snapshots.items():
        require(type(members) is list and 1 <= len(members) <= MAX_CONTEXT, 'Bounded component members')
        require(all(type(s) is dict and set(s) == SNAPSHOT_KEYS for s in members), 'Closed source snapshots')
        ids = [s['id'] for s in members]
        require(all(type(i) is str and ID.fullmatch(i) for i in ids) and ids == sorted(set(ids))
            and family == 'component:' + sha(encoded(ids).encode()), 'Exact sorted family identity')
        for source in members:
            ident = source['id']; require(ident not in by_id, 'Unique complete context IDs')
            require(source['kind'] in ('text', 'image', 'sequence', 'mesh', 'pointcloud'), 'Known snapshot kind')
            integer(source['revision'], 'Context revision')
            require(type(source['source_available']) is bool and source['source_lineage_known'] is True,
                'Typed known context lineage')
            require(source['source_split'] in ('unassigned', *SPLITS), 'Context split')
            strings(source['groups'], 'Context groups'); strings(source['parents'], 'Context parents', True)
            require(type(source['content_hash']) is str and (not source['content_hash'] or HASH.fullmatch(source['content_hash'])), 'Context content hash')
            require(source['pixel_hash'] is None or type(source['pixel_hash']) is str and HASH.fullmatch(source['pixel_hash']), 'Context pixel hash')
            if source['kind'] == 'text':
                require(type(source['source_revision']) is int and source['source_revision'] == 1
                    and type(source['source_sha256']) is str and HASH.fullmatch(source['source_sha256'])
                    and source['pixel_hash'] is source['book_id'] is source['session_id'] is None, 'Text context identity')
            elif source['kind'] in ('sequence', 'mesh', 'pointcloud'):
                require(type(source['source_revision']) is int and source['source_revision'] == 1
                    and source['source_sha256'] == source['content_hash'] and HASH.fullmatch(source['content_hash'])
                    and (source['kind'] == 'pointcloud' or source['source_split'] == 'unassigned')
                    and source['pixel_hash'] is source['book_id'] is source['session_id'] is None, 'Immutable context identity')
            elif source['source_available']:
                integer(source['source_revision'], 'Image context revision')
                require(type(source['source_sha256']) is str and HASH.fullmatch(source['source_sha256']), 'Image raw hash')
            else:
                require(source['source_revision'] is source['source_sha256'] is None, 'Deleted image identity')
            by_id[ident] = source; family_by_id[ident] = family
            key = 'id:' + ident; root(key)
            links = ['group:' + g for g in source['groups']] + ['id:' + p for p in source['parents']]
            if source['content_hash']: links.append('content:' + source['kind'] + ':' + source['content_hash'])
            if source['pixel_hash']: links.append('pixels:' + source['pixel_hash'])
            if source['kind'] == 'image':
                require(type(source['book_id']) is str and type(source['session_id']) is str, 'Image lineage strings')
                links.append('legacy:' + ('book:' + source['book_id'] if source['book_id'] else 'session:' + source['session_id']))
            for link in links: join(key, link)
    graph_families = {}
    for ident in by_id: graph_families.setdefault(root('id:' + ident), set()).add(family_by_id[ident])
    require(all(len(v) == 1 for v in graph_families.values()) and len(graph_families) == len(snapshots), 'Declared known graph closure')
    assignments = manifest['assignments']; ids = {row['id'] for row in rows}
    require(type(assignments) is dict and set(assignments) == ids and all(v in SPLITS for v in assignments.values()), 'Exact selected split assignments')
    require(ids <= by_id.keys() and all(p in by_id for s in by_id.values() for p in s['parents']),
        'Every selected source and retained parent has context')
    for family, members in snapshots.items():
        selected = [s['id'] for s in members if s['id'] in ids]
        fixed = sorted({s['source_split'] for s in members if s['source_split'] in SPLITS})
        require(selected and len({assignments[i] for i in selected}) == 1 and len(fixed) <= 1
            and (not fixed or assignments[selected[0]] == fixed[0]), 'Whole family/fixed split')
    for row in rows:
        require(encoded({k: row[k] for k in SNAPSHOT_KEYS}) == encoded(by_id[row['id']]), 'Selected snapshot equality')
    return family_by_id, by_id

def allocation_oracle(manifest, family_by_id):
    report = manifest['split_report']
    require(type(report) is dict and set(report) == {'requested_percentages', 'actual_counts', 'independent_components', 'note'},
        'Exact existing allocator report schema')
    ratios = report['requested_percentages']
    require(type(ratios) is dict and set(ratios) == set(SPLITS)
        and all(type(n) is int and 0 <= n <= 100 for n in ratios.values()) and sum(ratios.values()) == 100,
        'Exact bounded active split ratios')
    families = {}
    for row in manifest['records']: families.setdefault(family_by_id[row['id']], []).append(row['id'])
    active = [s for s in SPLITS if ratios[s]]
    require(len(families) >= len(active), 'Enough active whole families')
    assigned = {}; counts = {}; pending = []
    for family, ids in families.items():
        fixed = {s['source_split'] for s in manifest['protected_components'][family] if s['source_split'] in SPLITS}
        require(len(fixed) <= 1, 'No conflicting fixed source splits')
        if fixed:
            split = next(iter(fixed)); require(ratios[split] > 0, 'Fixed split has active weight')
            assigned.update({i: split for i in ids}); counts[split] = counts.get(split, 0) + len(ids)
        else: pending.append(ids)
    require(len(pending) >= sum(not counts.get(s, 0) for s in active), 'Enough free active families')
    pending.sort(key=lambda ids: (-len(ids), sha((str(manifest['seed']) + ':' + ','.join(sorted(ids))).encode())))
    for index, ids in enumerate(pending):
        empty = [s for s in active if not counts.get(s, 0)]
        choices = empty if len(pending) - index == len(empty) else active
        split = max(choices, key=lambda s: (ratios[s] * len(manifest['records']) / 100 - counts.get(s, 0), -SPLITS.index(s)))
        assigned.update({i: split for i in ids}); counts[split] = counts.get(split, 0) + len(ids)
    expected = dict(requested_percentages=ratios, actual_counts=counts, independent_components=len(families),
        note='Whole connected groups are indivisible; existing source splits are preserved. Requested percentages are targets, not exact quotas.')
    require(encoded(report) == encoded(expected) and assigned == manifest['assignments'], 'Independent complete split allocation')


def native_scalar(token,dtype):
    """Exact Decimal/Fraction nearest-even native bits, independent of decoder."""
    require(NUMBER.fullmatch(token),'Finite decimal native grammar')
    value=float(token);decimal=Decimal(token)
    require(math.isfinite(value) and abs(value)<=1e12 and (value!=0 or decimal==0),'Finite representable magnitude')
    fmt,word=('f','I') if dtype=='float' else ('d','Q')
    near=struct.unpack('<'+word,struct.pack('<'+fmt,abs(value)))[0]
    exact=Fraction(decimal.copy_abs())
    def binary(bits):return struct.unpack('<'+fmt,struct.pack('<'+word,bits))[0]
    bits=min(range(max(0,near-1),near+2),key=lambda b:(abs(exact-Fraction.from_float(binary(b))),b%2))
    native=binary(bits);require(not exact or native!=0,'No nonzero native underflow')
    if token.startswith('-'):native=-native
    # Preserve the existing mesh policy, separate from point-cloud signed zero.
    if native==0:native=0.
    return native,struct.pack('<'+fmt,native)


def raw_pair_oracle(raw,sidecar_raw):
    require(0<len(raw)<=2*1024*1024 and 0<len(sidecar_raw)<=32*1024,'Bounded authoritative raw pair')
    sidecar=decode(sidecar_raw)
    require(type(sidecar)is dict and set(sidecar)=={'format','geometry_file','geometry_bytes','geometry_sha256','units','coordinate_system','provenance'},'Closed original mesh sidecar')
    require(sidecar['format']=='tuldok_mesh_v1' and sidecar['geometry_file']=='mesh.ply'
        and type(sidecar['geometry_bytes'])is int and sidecar['geometry_bytes']==len(raw) and sidecar['geometry_sha256']==sha(raw),'Original ASCII source version/hash/size')
    require(sidecar['units'] in ('m','cm','mm'),'Declared units')
    frame=sidecar['coordinate_system'];require(type(frame)is dict and set(frame)=={'frame','handedness','up_axis'}
        and type(frame['frame'])is str and frame['frame'].strip() and len(frame['frame'])<=120 and frame['handedness'] in ('left','right') and frame['up_axis'] in ('x','y','z'),'Closed declared frame')
    prov=sidecar['provenance'];require(type(prov)is dict and set(prov)=={'source','revision','license','description'}
        and all(type(v)is str and v.strip() and len(v)<=1000 for v in prov.values()),'Closed declared original provenance')
    require(raw.endswith(b'\n') and raw.count(b'\n')<=20000+40000+16384,'Complete bounded ASCII lines')
    require(not any(b<32 and b not in (9,10,13) for b in raw) and b'\r' not in raw.replace(b'\r\n',b''),'Supported ASCII controls')
    lines=raw.decode('ascii').splitlines();require(all(len(l)<=1024 for l in lines) and lines[:2]==['ply','format ascii 1.0'] and 'end_header' in lines,'Exact ASCII header and line cap')
    end=lines.index('end_header');require(sum(map(len,raw.splitlines(keepends=True)[:end+1]))<=16384,'Bounded ASCII header')
    head=[l.split() for l in lines[2:end] if not l.startswith('comment ')]
    require(head and len(head[0])==3 and head[0][:2]==['element','vertex'] and INTEGER.fullmatch(head[0][2]),'Bounded vertex element')
    count=int(head[0][2]);require(1<=count<=20000,'Vertex count cap')
    props=[];cursor=1
    while cursor<len(head) and head[cursor][:1]==['property']:
        require(len(head[cursor])==3 and head[cursor][1] in ('float','double'),'Scalar native vertex properties')
        props.append(dict(name=head[cursor][2],dtype=head[cursor][1]));cursor+=1
    require([p['name'] for p in props] in (['x','y','z'],['x','y','z','nx','ny','nz']),'Named exact geometry axes')
    require(cursor<len(head) and len(head[cursor])==3 and head[cursor][:2]==['element','face'] and INTEGER.fullmatch(head[cursor][2]),'Face element')
    face_count=int(head[cursor][2]);require(1<=face_count<=40000 and head[cursor+1:]==[['property','list','uchar','int','vertex_indices']],'Exact ordered triangle profile')
    body=lines[end+1:];require(len(body)==count+face_count,'Complete vertex/face rows')
    vertices=[];columns={p['name']:bytearray() for p in props}
    for line in body[:count]:
        tokens=line.split();require(len(tokens)==len(props),'Exact native vertex row')
        values=[]
        for token,p in zip(tokens,props):
            value,wire=native_scalar(token,p['dtype']);values.append(value);columns[p['name']].extend(wire)
        vertices.append(values)
    faces=[];seen=set()
    for line in body[count:]:
        tokens=line.split();require(len(tokens)==4 and tokens[0]=='3' and all(INTEGER.fullmatch(t) for t in tokens[1:]),'Exact ordered uchar/int triangle')
        face=[int(t) for t in tokens[1:]];require(len(set(face))==3 and all(i<count for i in face),'Distinct bounded triangle indices')
        key=tuple(sorted(face));require(key not in seen,'No duplicate unordered triangle');seen.add(key)
        a,b,c=[vertices[i][:3] for i in face];u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
        require(any(x!=0 for x in (u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])),'Nonzero representable triangle cross product')
        faces.append(face)
    columns['vertex_indices']=b''.join(struct.pack('<3i',*face) for face in faces)
    bounds=dict(min=[min(v[i] for v in vertices) for i in range(3)],max=[max(v[i] for v in vertices) for i in range(3)])
    family=sha(encoded(dict(vertices=[v[:3] for v in vertices],faces=faces,units=sidecar['units'],coordinate_system=frame)).encode())
    metadata=dict(manifest=sidecar,manifest_sha256=sha(sidecar_raw),properties=props,vertex_count=count,triangle_count=face_count,bounds=bounds,
        provided_normals=len(props)==6,protected_groups=['mesh-source:'+sha(raw),'mesh-family:'+family],
        scope='whole static mesh; geometry transport and inspection; no simulation or training qualification')
    return dict(metadata=metadata,properties=props,vertices=vertices,faces=faces,columns={k:bytes(v) for k,v in columns.items()})


def inspect_archive(raw,expected=None):
    values=zip_payloads(raw);require('manifest.json' in values and len(values['manifest.json'])<=MAX_METADATA,'Bounded complete manifest')
    m=decode(values['manifest.json']);require(type(m)is dict and set(m)=={'schema_version','seed','split_report','coordinate_contract','limitations','records','protected_components','vocabulary'},'Closed full-proof canonical manifest')
    require(type(m['schema_version'])is int and m['schema_version']==1 and type(m['seed'])is int and 0<=m['seed']<=2**32-1 and m['vocabulary']==[],'Version/seed/no inferred taxonomy')
    require(type(m['coordinate_contract'])is str and type(m['limitations'])is list and all(type(v)is str for v in m['limitations']),'Explicit canonical scope')
    rows=m['records'];require(type(rows)is list and 1<=len(rows)<=MAX_RECORDS and all(type(r)is dict and set(r)==ROW_KEYS for r in rows),'Closed whole-mesh records')
    ids=[r['id'] for r in rows];require(all(type(i)is str and ID.fullmatch(i) for i in ids) and len(set(ids))==len(ids),'Unique record IDs')
    if expected is not None:
        require(type(expected)is list and len(expected)==len(rows),'Expected full source row count');byid={r['id']:r for r in expected};require(set(byid)==set(ids),'Expected original row IDs')
        for r in rows:
            e=byid[r['id']];require(set(e) in (ROW_KEYS,ROW_KEYS-{'asset','asset_sha256','split','export_group'}) and encoded(e)==encoded({k:r[k] for k in e}),'Exact independent full owner snapshots')
    require(set(values)=={'manifest.json','README.txt'}|{s+'/'+name for s in SPLITS for name in ('records.jsonl','coco.json')}|{'assets/'+i+'.zip' for i in ids},'Closed canonical archive')
    total=0;pairs={};oracles={}
    for r in rows:
        require(r['kind']=='mesh' and r['task']=='mesh_geometry' and r['review']=='human_reviewed' and r['source_available'] is r['source_lineage_known'] is True,'Available human-reviewed whole mesh')
        integer(r['revision'],'Record revision');require(type(r['source_revision'])is int and r['source_revision']==1,'Immutable source revision')
        require(all(r[k] is None for k in ('text','pixel_hash','book_id','session_id','width','height','corner_annotation')) and r['source_split']=='unassigned','Mesh source identity')
        strings(r['groups'],'Groups');strings(r['parents'],'Parents',True)
        require(type(r['annotation'])is dict and set(r['annotation'])=={'note'} and type(r['annotation']['note'])is str and 0<len(r['annotation']['note'])<=4000 and r['annotation']['note'].strip()==r['annotation']['note'],'Nonempty inspection note')
        require(r['split'] in SPLITS and type(r['provenance'])is dict and type(r['provenance'].get('rights'))is str and 0<len(r['provenance']['rights'])<=1000,'Split and retained rights claim')
        asset='assets/'+r['id']+'.zip';bundle=values[asset];total+=len(bundle)
        require(r['asset']==asset and len(bundle)<=2*1024*1024+32*1024+1024 and total<=MAX_BUNDLES and sha(bundle)==r['asset_sha256']==r['content_hash']==r['source_sha256'],'Full bounded immutable bundle hashes')
        pair=zip_payloads(bundle,2,2*1024*1024+32*1024+1024);require(list(pair)==['mesh.ply','mesh.json'],'Ordered exact original raw pair')
        oracle=raw_pair_oracle(pair['mesh.ply'],pair['mesh.json'])
        require(encoded(r['mesh'])==encoded(dict(oracle['metadata'],bundle_bytes=len(bundle))) and set(oracle['metadata']['protected_groups'])<=set(r['groups']),'Exact independent raw metadata and protected families')
        pairs[r['id']]=pair;oracles[r['id']]=oracle
    for s in SPLITS:
        stream=values[s+'/records.jsonl'];require(len(stream)<=MAX_METADATA and (not stream or stream.endswith(b'\n')),'Bounded complete JSONL')
        lines=stream.splitlines();require(len(lines)<=64 and all(0<len(l)<=256*1024 for l in lines),'Bounded complete lines')
        require(encoded([decode(l) for l in lines])==encoded([r for r in rows if r['split']==s]),'Exact split/source association')
        coco=decode(values[s+'/coco.json']);require(len(values[s+'/coco.json'])<=4096 and set(coco)=={'info','licenses','images','annotations','categories'} and all(coco[k]==[] for k in ('licenses','images','annotations','categories')),'Empty mesh COCO without invented targets')
    proof=dict(m,assignments={r['id']:r['split'] for r in rows});family,context=graph_oracle(proof,rows);allocation_oracle(proof,family)
    require(all(r['export_group']==family[r['id']] for r in rows),'Exact declared export family')
    return dict(manifest=m,payloads=values,pairs=pairs,oracles=oracles,context=context,family_by_id=family)


def identity(path):
    b=capture(path,MAX_PHYSICAL);return dict(path=str(path),bytes=len(b),sha256=sha(b))


def pins():
    import numpy as np
    import plyfile
    value=decode((ROOT/'tests/pointcloud-consumer-pins.json').read_bytes())
    require(np.__version__==value['numpy'] and importlib.metadata.version('plyfile')==value['plyfile']['version'],'Actual released reader versions')
    require(sha(Path(plyfile.__file__).read_bytes())==value['plyfile']['module_sha256'],'Actual installed exact reader source')
    return np,plyfile,dict(value,module=identity(Path(plyfile.__file__)))


def verify_fields(fields,oracle,np):
    names=[p['name'] for p in oracle['properties']]+['vertex_indices'];require(type(fields)is dict and list(fields)==names,'Separate named vertex properties and topology')
    reports=[]
    for name in names:
        a=fields[name]
        dtype='<i4' if name=='vertex_indices' else DTYPES[next(p['dtype'] for p in oracle['properties'] if p['name']==name)]
        shape=(len(oracle['faces']),3) if name=='vertex_indices' else (len(oracle['vertices']),)
        require(isinstance(a,np.ndarray) and a.dtype.str==dtype and a.shape==shape and a.tobytes()==oracle['columns'][name],'Exact native dtype/axes/order/bits: '+name)
        reports.append(dict(name=name,shape=list(a.shape),dtype=a.dtype.str,native_sha256=sha(a.tobytes()),native_hex=a.tobytes().hex() if a.size<=32 else None,values=a.tolist() if a.size<=32 else None))
    return reports


def binary_file_oracle(path,oracle,row,release_sha,sidecar):
    raw=capture(path,MAX_BINARY);marker=b'end_header\n';end=raw.find(marker)
    require(0<end and end+len(marker)<=MAX_BINARY_HEADER,'Bounded exact binary header')
    end+=len(marker);lines=raw[:end].decode('ascii').splitlines()
    require(lines[:2]==['ply','format binary_little_endian 1.0'],'Standard supported binary little-endian PLY')
    properties=[l for l in lines[2:-1] if not l.startswith('comment ')]
    expected=['element vertex '+str(len(oracle['vertices']))]+['property '+p['dtype']+' '+p['name'] for p in oracle['properties']]
    expected+=['element face '+str(len(oracle['faces'])),'property list uchar int vertex_indices']
    require(properties==expected,'Exact scalar axes/dtypes and uchar/int topology header')
    comments={}
    for line in lines[2:-1]:
        if line.startswith('comment tuldok_'):
            key,_,value=line[len('comment tuldok_'):].partition(' ');require(key not in comments,'Unique derivation comment');comments[key]=value
    provenance=dict(representation='derived native-value exact binary PLY; original ASCII remains authoritative',release_sha256=release_sha,
        bundle_sha256=row['content_hash'],original_geometry_sha256=row['mesh']['manifest']['geometry_sha256'],original_manifest_sha256=sha(sidecar),
        record_id=row['id'],revision=str(row['revision']),source_revision=str(row['source_revision']),split=row['split'],original_mesh_json_base64=base64.b64encode(sidecar).decode())
    require(comments==provenance and base64.b64decode(comments['original_mesh_json_base64'],validate=True)==sidecar,'Exact original sidecar and immutable source/release/provenance links')
    body=bytearray()
    for vertex in oracle['vertices']:
        for value,p in zip(vertex,oracle['properties']):body.extend(struct.pack('<'+('f' if p['dtype']=='float' else 'd'),value))
    for face in oracle['faces']:body.extend(struct.pack('<B3i',3,*face))
    require(raw[end:]==bytes(body),'Independent exact interleaved native binary scalar/topology payload')
    return dict(file=identity(path),source_geometry_sha256=provenance['original_geometry_sha256'],original_sidecar_sha256=sha(sidecar),
        comments=comments,header_bytes=end,body_sha256=sha(bytes(body)),source_byte_identical=False)


def actual_binary_read(path,oracle,np,plyfile):
    with path.open('rb') as source:actual=plyfile.PlyData.read(source,mmap=False)
    require(actual.text is False and actual.byte_order=='<' and [e.name for e in actual.elements]==['vertex','face'],'Actual released binary reader elements/order/endianness')
    vertex=actual['vertex'].data;require(vertex.dtype.names==tuple(p['name'] for p in oracle['properties']),'Actual native vertex axes')
    face=actual['face'];require(face.data.dtype.names==('vertex_indices',) and len(face.data)==len(oracle['faces']),'Actual topology element/face count')
    prop=face.properties[0];require(prop.name=='vertex_indices' and prop.len_dtype=='u1' and prop.val_dtype=='i4','Actual uchar count/int topology type')
    require(all(a.dtype.str=='<i4' and a.shape==(3,) for a in face.data['vertex_indices']),'Actual triangular native list axes')
    fields={name:vertex[name] for name in vertex.dtype.names};fields['vertex_indices']=np.stack(face.data['vertex_indices'])
    return actual,dict(file=identity(path),attributes=verify_fields(fields,oracle,np),status='PASS')


def exercise(path,out,np,plyfile,expected=None):
    from native_mesh_dataset import NativeMeshDataset,NativeMeshError
    raw=capture(path,MAX_PHYSICAL);checked=inspect_archive(raw,expected);rows=checked['manifest']['records'];out.mkdir(parents=True,exist_ok=True)
    captured=out/'captured-release.zip';captured.write_bytes(raw)
    context=[s for family in sorted(checked['manifest']['protected_components']) for s in checked['manifest']['protected_components'][family]]
    samples=[]
    for split in SPLITS:
        dataset=NativeMeshDataset(captured,sha256=sha(raw),split=split);selected=[r for r in rows if r['split']==split]
        require(len(dataset)==len(selected),'Whole mesh frozen explicit split sample count')
        for index,row in enumerate(selected):
            oracle=checked['oracles'][row['id']];sample=dataset[index];require(set(sample)=={'fields','metadata'},'Closed native mesh sample')
            attrs=verify_fields(sample['fields'],oracle,np);meta=sample['metadata']
            require(set(meta)=={'schema','release_sha256','split','array_axes','properties','record','declared_family_context','units','coordinate_system','attribute_semantics','derivation','consumer','limitations'},'Closed complete sample metadata')
            require(meta['schema']=='native_mesh_sample_v1' and meta['release_sha256']==sha(raw) and meta['split']==split
                and meta['array_axes']==dict(vertex_properties=['vertex'],vertex_indices=['triangle','corner']) and encoded(meta['record'])==encoded(row),'Exact native axes and frozen full owner row')
            require(meta['properties']==[{k:a[k] for k in ('name','shape','dtype')} for a in attrs]
                and encoded(meta['declared_family_context'])==encoded(context),'Exact native descriptors and complete known family context')
            require(meta['units']==row['mesh']['manifest']['units'] and encoded(meta['coordinate_system'])==encoded(row['mesh']['manifest']['coordinate_system']),'Units/frame retained')
            require(meta['attribute_semantics']==dict(coordinates='xyz retain declared native units and frame',normals='dimensionless provided native values; magnitude is retained',topology='ordered zero-based triangle corners; no reindexing or winding changes'),'Explicit native attribute/topology semantics')
            require(meta['consumer']==dict(plyfile='1.1.3',plyfile_module_sha256=sha(Path(plyfile.__file__).read_bytes()),numpy='2.5.3') and type(meta['limitations'])is list,'Pinned reader identity and explicit limitations')
            ply=out/(split+'-'+str(index)+'.ply');ply.write_bytes(b'previous binary output');dataset.write_ply(ply,index=index)
            binary=binary_file_oracle(ply,oracle,row,sha(raw),checked['pairs'][row['id']]['mesh.json'])
            expected_derivation=dict(binary['comments'],revision=row['revision'],source_revision=row['source_revision'],
                format='binary_little_endian PLY 1.0',sha256=binary['file']['sha256'],bytes=binary['file']['bytes'],
                zero_semantics='existing mesh decoder canonicalizes native zero to positive zero')
            require(encoded(meta['derivation'])==encoded(expected_derivation),'Complete exact derived representation and original source identity')
            actual,reading=actual_binary_read(ply,oracle,np,plyfile)
            writer=out/(split+'-'+str(index)+'-external-roundtrip.ply');actual.write(str(writer));rewritten=binary_file_oracle(writer,oracle,row,sha(raw),checked['pairs'][row['id']]['mesh.json'])
            _,again=actual_binary_read(writer,oracle,np,plyfile)
            target=out/(split+'-'+str(index)+'.npz');target.write_bytes(b'previous NPZ output');dataset.write_npz(target,index=index);require(target.stat().st_size<=MAX_NPZ,'Complete NPZ byte bound')
            with np.load(target,allow_pickle=False) as z:
                require(set(z.files)==set(sample['fields'])|{'metadata_utf8'},'Closed pickle-free numeric and UTF8 metadata keys')
                verify_fields({name:z[name] for name in sample['fields']},oracle,np)
                require(z['metadata_utf8'].dtype==np.dtype('uint8') and z['metadata_utf8'].ndim==1 and encoded(decode(z['metadata_utf8'].tobytes()))==encoded(meta),'Exact metadata UTF8 bytes in NPZ')
            before=encoded(meta);sample['fields']['x'][0]=123;sample['fields']['vertex_indices'][0,0]=-1;meta['record']['name']='caller mutation'
            fresh=dataset[index];verify_fields(fresh['fields'],oracle,np);require(encoded(fresh['metadata'])==before,'Fresh independent fields and deep metadata')
            samples.append(dict(id=row['id'],split=split,index=index,attributes=attrs,npz=identity(target),derived_ply=binary,
                actual_binary_read=reading,external_writer_roundtrip=rewritten,external_writer_reader=again,metadata=fresh['metadata']))
        if not selected:
            for extension,write in (('npz',dataset.write_npz),('ply',dataset.write_ply)):
                empty=out/(split+'-empty.'+extension);empty.write_bytes(b'unchanged empty split')
                try:write(empty)
                except NativeMeshError:pass
                else:raise ValueError('Empty split wrote '+extension)
                require(empty.read_bytes()==b'unchanged empty split','Empty split atomic refusal')
        try:dataset[True]
        except NativeMeshError:pass
        else:raise ValueError('Boolean sample index accepted')
        if selected:
            for write in (dataset.write_ply,dataset.write_npz):
                try:write(captured)
                except NativeMeshError:pass
                else:raise ValueError('Derived output overwrote authoritative release')
                require(captured.read_bytes()==raw,'Source byte custody')
    return dict(status='PASS',release=identity(path),records=len(rows),families=len(checked['manifest']['protected_components']),
        declared_context_members=len(context),actual_external_file_reads=2*len(samples),actual_external_file_writes=len(samples),samples=samples),checked


def synchronize(values,m):
    values['manifest.json']=encoded(m).encode()
    for split in SPLITS:values[split+'/records.jsonl']=b''.join((encoded(r)+'\n').encode() for r in m['records'] if r['split']==split)


def malformed_controls(raw,out):
    from native_mesh_dataset import NativeMeshDataset,NativeMeshError
    original=zip_payloads(raw);controls=[]
    for label in ('missing-proof','asset-hash','truncated-jsonl','wrong-native-dtype','nonfinite-raw','graph-bridge'):
        values=dict(original);m=decode(values['manifest.json'])
        if label=='missing-proof':del m['protected_components']
        elif label=='asset-hash':m['records'][0]['asset_sha256']='0'*64
        elif label=='graph-bridge':
            r=m['records'][0];r['parents'].append('0'*32)
            for members in m['protected_components'].values():
                for source in members:
                    if source['id']==r['id']:source['parents']=list(r['parents'])
        elif label in ('wrong-native-dtype','nonfinite-raw'):
            r=m['records'][0];pair=zip_payloads(values[r['asset']],2)
            if label=='wrong-native-dtype':pair['mesh.ply']=pair['mesh.ply'].replace(b'property float ',b'property uchar ',1).replace(b'property double ',b'property uchar ',1)
            else:
                lines=pair['mesh.ply'].splitlines(keepends=True);end=lines.index(b'end_header\n');parts=lines[end+1].split();parts[0]=b'nan';lines[end+1]=b' '.join(parts)+b'\n';pair['mesh.ply']=b''.join(lines)
            side=decode(pair['mesh.json']);side.update(geometry_bytes=len(pair['mesh.ply']),geometry_sha256=sha(pair['mesh.ply']));pair['mesh.json']=encoded(side).encode()
            bundle=archive_from(pair);values[r['asset']]=bundle
            r['content_hash']=r['source_sha256']=r['asset_sha256']=sha(bundle)
            for members in m['protected_components'].values():
                for source in members:
                    if source['id']==r['id']:source['content_hash']=source['source_sha256']=sha(bundle)
        synchronize(values,m)
        if label=='truncated-jsonl':
            name=next(s+'/records.jsonl' for s in SPLITS if values[s+'/records.jsonl']);values[name]=values[name][:-1]
        damaged=archive_from(values);path=out/(label+'.zip');path.write_bytes(damaged)
        try:inspect_archive(damaged)
        except ValueError:pass
        else:raise ValueError('Independent oracle accepted '+label)
        try:NativeMeshDataset(path,sha256=sha(damaged),split='train')
        except NativeMeshError as error:controls.append(dict(case=label,status='REFUSED',reason=str(error),artifact=identity(path)))
        else:raise ValueError('Production consumer accepted '+label)
    return controls


def numeric_controls(out,np,plyfile):
    """Actual admitted/frozen production samples, not parser-only substitutes."""
    from app import Dataset
    from native_mesh_fixture import pair,admit,review,freeze
    controls=[('positive-lower-neighbor','1.0000000596046448',0x3f800001),
        ('positive-upper-neighbor','1.0000001788139343',0x3f800001),
        ('negative-lower-neighbor','-1.0000000596046448',0xbf800001),
        ('negative-upper-neighbor','-1.0000001788139343',0xbf800001),
        ('positive-lower-tie','1.000000059604644775390625',0x3f800000),
        ('positive-upper-tie','1.000000178813934326171875',0x3f800002),
        ('negative-lower-tie','-1.000000059604644775390625',0xbf800000),
        ('negative-upper-tie','-1.000000178813934326171875',0xbf800002),
        ('positive-subnormal','1e-45',1),('negative-subnormal','-1e-45',0x80000001),
        ('positive-zero','0.0',0),('negative-zero','-0.0',0)]
    reports=[]
    for label,token,bits in controls:
        folder=out/label;folder.mkdir(parents=True,exist_ok=True)
        owner=Dataset(str(folder/'checker-numeric-owner'))
        try:
            raw,sidecar=pair(token=token);oracle=raw_pair_oracle(raw,sidecar)
            require(oracle['columns']['x'][:4]==struct.pack('<I',bits),'Literal independently expected native control bits')
            row=review(owner.workbench,admit(owner.workbench,raw,sidecar));release,preview=freeze(owner,[row],ratios=dict(train=100,validation=0,test=0))
            path=folder/'release.zip';path.write_bytes(release)
        finally:owner.close()
        report,_=exercise(path,folder/'consumer',np,plyfile,[row])
        require(report['records']==1 and report['samples'][0]['attributes'][0]['native_hex'].startswith(struct.pack('<I',bits).hex()),'Actual production/native target control bits')
        reports.append(dict(case=label,token=token,expected_float32_bits=format(bits,'08x'),fixture_origin='Root-authored analytic mixed-native triangle, exact source-derived decimal token control',status='PASS',consumer=report))
    return reports


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--release','--archive',dest='release',type=Path)
    parser.add_argument('--expected-rows','--expected',dest='expected',type=Path)
    args=parser.parse_args();out=output_preflight(args.output)
    sys.path.insert(0,str(ROOT));sys.path.insert(0,str(FIXTURES))
    np,plyfile,reader=pins()
    from app import Dataset
    from native_mesh_fixture import populate,freeze,admit,review,ref
    expected=decode(capture(args.expected,MAX_METADATA)) if args.expected else None
    if type(expected)is dict:expected=expected['records']
    bridge=None
    if args.release:path=args.release
    else:
        first=Dataset(str(out/'checker-owner-first'))
        try:
            rows,bridge=populate(first);raw,preview=freeze(first,rows);path=out/'checker-first-release.zip';path.write_bytes(raw);expected=rows
        finally:first.close()
    result=dict(status='PASS',scope='Existing whole mesh canonical transport, exact native-derived standard binary reader/writer and pickle-free NPZ; no geometry/training/simulation qualification.',
        packet_origin='actual_browser_or_supplied_owner_release' if args.release else 'checker_authored_actual_owner_fixture',
        role='QA checker authored independently of root-owned production module; independent raw Fraction/native/topology, archive/schema, graph and allocator oracles precede production execution.',
        pins=reader,consumer_limits=dict(records=64,physical_and_logical_release_bytes=MAX_PHYSICAL,metadata_bytes=MAX_METADATA,context_members=5000,selected_bundles_bytes=MAX_BUNDLES,npz_bytes=MAX_NPZ,binary_ply_bytes=MAX_BINARY,binary_header_bytes=MAX_BINARY_HEADER))
    result['first'],checked=exercise(path,out/'first',np,plyfile,expected);first_raw=capture(path,MAX_PHYSICAL);first_rows=checked['manifest']['records']
    second=Dataset(str(out/'checker-owner-second'));transfer=[]
    try:
        rows=[]
        for original in first_rows:
            pair=checked['pairs'][original['id']];row=admit(second.workbench,pair['mesh.ply'],pair['mesh.json'])
            require(row['id'] not in {r['id'] for r in first_rows} and row['review']=='draft' and row['annotation'] is None
                and row['provenance']['rights']=='unknown' and row['parents']==[] and row['source_split']=='unassigned','New owner local draft/unknown rights/no inherited parent, review or assigned split')
            require(encoded(row['mesh'])==encoded(original['mesh']) and second.workbench.asset(row['id'])[0]==checked['payloads'][original['asset']],'Exact original raw pair and native metadata')
            rows.append(row);transfer.append(dict(original_id=original['id'],new_id=row['id'],admitted=copy.deepcopy(row)))
        require(len({r['id'] for r in rows})==len(rows),'Unique disjoint fresh-owner IDs')
        request=dict(items=[ref(r) for r in rows],ratios=dict(train=50,validation=50,test=0),seed=87)
        require(not second.releases.preview(request)['eligible'],'Unreviewed raw pairs cannot freeze')
        rows=[second.workbench.save(r['id'],dict(ref(r),task='mesh_geometry',groups=r['groups'],
            annotation={'note':'Authored saved draft mesh transport QA; no simulation or training qualification.'},review='draft')) for r in rows]
        rows=[second.workbench.get(r['id']) for r in rows]
        require(all(r['review']=='draft' for r in rows),'Actual saved/reopened draft note')
        for proof,row in zip(transfer,rows):proof['reopened_draft']=copy.deepcopy(row)
        rows=[review(second.workbench,r) for r in rows];raw,preview=freeze(second,rows);second_path=out/'checker-second-release.zip';second_path.write_bytes(raw)
        result['second'],other=exercise(second_path,out/'second',np,plyfile,rows)
        for proof,row in zip(transfer,rows):
            proof['reviewed']=copy.deepcopy(row);require(other['pairs'][row['id']]==checked['pairs'][proof['original_id']],'Byte-exact original ASCII sidecar frozen reexport')
    finally:second.close()
    require(capture(path,MAX_PHYSICAL)==first_raw,'Supplied original release remains unchanged')
    result['transfer']=dict(records=transfer,byte_exact_original_raw_pairs=True,whole_declared_families=True,
        caveat='Mesh sidecar has no fixed split; fresh owner allocates whole families from its own context. Original raw pairs do not transfer sender local IDs, parents, arbitrary groups, split assignment, rights notes or human annotations/review.')
    result['second_packet_origin']='checker_created_fresh_owner_original_raw_pair_reimport'
    result['malformed_controls']=malformed_controls(first_raw,out)
    if bridge is not None:
        result['known_deleted_parent']=bridge
        result['numeric_controls']=numeric_controls(out/'numeric-controls',np,plyfile)
    else:result['numeric_controls']=[]
    result['records']=result['first']['records'];result['declared_context_members']=result['first']['declared_context_members'];result['release_sha256']=sha(first_raw);result['samples']=result['first']['samples']
    result['actual_external_file_reads']=result['first']['actual_external_file_reads']+result['second']['actual_external_file_reads']+sum(c['consumer']['actual_external_file_reads'] for c in result['numeric_controls'])
    (out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print('Native whole mesh exact binary reader/writer, NPZ and second-owner raw roundtrip PASS: '+str(out))


if __name__=='__main__':main()

