"""Independent canonical point/family/native/NPZ oracle; no models or training.

Archive and native-bit checks do not call the production dataset validator.
Only then is the actual reusable dataset and pinned file reader exercised.
"""
import argparse
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
SPLITS=('train','validation','test')
ID=re.compile(r'[a-f0-9]{32}')
HASH=re.compile(r'[a-f0-9]{64}')
NUMBER=re.compile(r'^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$')
INTEGER=re.compile(r'^(?:0|[1-9][0-9]*)$')
SNAPSHOT_KEYS=set('id kind revision source_revision content_hash pixel_hash groups parents source_available source_lineage_known source_split source_sha256 book_id session_id'.split())
ROW_KEYS=SNAPSHOT_KEYS|set('annotation asset asset_sha256 corner_annotation created_at export_group height name pointcloud provenance review split task text updated_at width'.split())
DTYPES={'float':'<f4','double':'<f8','uchar':'|u1'}


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
    """Independent nearest-even oracle: compare three adjacent native candidates."""
    if dtype=='uchar':
        require(INTEGER.fullmatch(token) and int(token)<=255,'Unsigned RGB scalar')
        return int(token),bytes([int(token)])
    require(NUMBER.fullmatch(token),'Finite decimal scalar grammar')
    value=float(token);decimal=Decimal(token)
    require(math.isfinite(value) and abs(value)<=1e12 and (value!=0 or decimal==0),'Finite representable magnitude')
    if dtype=='double':return value,struct.pack('<d',value)
    rounded=struct.unpack('<I',struct.pack('<f',abs(value)))[0]
    exact=Fraction(decimal.copy_abs())
    candidates=range(max(0,rounded-1),rounded+2)
    bits=min(candidates,key=lambda n:(abs(exact-Fraction.from_float(struct.unpack('<f',struct.pack('<I',n))[0])),n%2))
    if token.startswith('-'):bits|=0x80000000
    raw=struct.pack('<I',bits);native=struct.unpack('<f',raw)[0]
    require(value==0 or native!=0,'No nonzero float32 underflow')
    require(raw==struct.pack('<f',value),'Point profile forbids external float32 double-rounding discrepancy')
    return native,raw


def raw_pair_oracle(raw,sidecar_raw):
    require(0<len(raw)<=2*1024*1024 and 0<len(sidecar_raw)<=32*1024,'Raw pair caps')
    sidecar=decode(sidecar_raw)
    require(type(sidecar)is dict and set(sidecar)=={'format','geometry_file','geometry_bytes','geometry_sha256','units','coordinate_system','provenance','lineage'},'Closed source sidecar')
    require(sidecar['format']=='tuldok_pointcloud_v1' and sidecar['geometry_file']=='points.ply'
        and type(sidecar['geometry_bytes'])is int and sidecar['geometry_bytes']==len(raw)
        and sidecar['geometry_sha256']==sha(raw),'Point source format/hash/count')
    require(sidecar['units'] in ('m','cm','mm'),'Source units')
    frame=sidecar['coordinate_system']
    require(type(frame)is dict and set(frame)=={'frame','handedness','up_axis'}
        and type(frame['frame'])is str and frame['frame'].strip() and len(frame['frame'])<=120
        and frame['handedness'] in ('left','right') and frame['up_axis'] in ('x','y','z'),'Declared frame')
    provenance=sidecar['provenance'];require(type(provenance)is dict and set(provenance)=={'source','revision','license','description'}
        and all(type(v)is str and v.strip() and len(v)<=1000 for v in provenance.values()),'Declared provenance')
    lineage=sidecar['lineage'];require(type(lineage)is dict and set(lineage)=={'namespace','source_id','family_id','split'},'Closed declared lineage')
    require(all(type(lineage[k])is str and 0<len(lineage[k])<=120 and lineage[k].strip()==lineage[k] for k in ('namespace','source_id','family_id'))
        and lineage['split'] in ('unassigned',*SPLITS),'Canonical lineage claims')
    require(raw.endswith(b'\n') and raw.count(b'\n')<=20000+16384,'Complete bounded point lines')
    require(not any(b<32 and b not in (9,10,13) for b in raw) and b'\r' not in raw.replace(b'\r\n',b''),'Point ASCII controls')
    lines=raw.decode('ascii').splitlines();require(all(len(l)<=1024 for l in lines),'PLY line cap')
    require(lines[:2]==['ply','format ascii 1.0'] and 'end_header' in lines,'ASCII PLY header')
    end=lines.index('end_header');require(sum(len(l) for l in raw.splitlines(keepends=True)[:end+1])<=16384,'PLY header cap')
    header=[l.split() for l in lines[2:end] if not l.startswith('comment ')]
    require(header and len(header[0])==3 and header[0][:2]==['element','vertex'] and INTEGER.fullmatch(header[0][2]),'Vertex-only header')
    count=int(header[0][2]);require(1<=count<=20000 and len(lines[end+1:])==count,'Exact whole point count')
    properties=[]
    for prop in header[1:]:
        require(len(prop)==3 and prop[0]=='property','Scalar vertex properties only')
        properties.append(dict(name=prop[2],dtype=prop[1]))
    names=[p['name'] for p in properties];xyz=['x','y','z'];normals=['nx','ny','nz'];colors=['red','green','blue']
    require(names in (xyz,xyz+normals,xyz+colors,xyz+normals+colors),'Exact complete named properties')
    require(all(p['dtype'] in (('uchar',) if p['name'] in colors else ('float','double')) for p in properties),'Exact source native dtypes')
    points=[];columns={p['name']:bytearray() for p in properties}
    for line in lines[end+1:]:
        tokens=line.split();require(len(tokens)==len(properties),'Exact point property count')
        values=[]
        for token,prop in zip(tokens,properties):
            native,wire=native_scalar(token,prop['dtype']);values.append(native);columns[prop['name']].extend(wire)
        points.append(values)
    bounds=dict(min=[min(p[i] for p in points) for i in range(3)],max=[max(p[i] for p in points) for i in range(3)])
    family=sha(encoded(dict(points=[[0. if v==0 else v for v in p[:3]] for p in points],units=sidecar['units'],coordinate_system=frame)).encode())
    link=lambda domain,key:sha(encoded([domain,lineage['namespace'],lineage[key]]).encode())
    groups=['pointcloud-source:'+sha(raw),'pointcloud-native:'+family,'pointcloud-origin:'+link('pointcloud-source-v1','source_id'),'pointcloud-family:'+link('pointcloud-family-v1','family_id')]
    metadata=dict(manifest=sidecar,manifest_sha256=sha(sidecar_raw),properties=properties,point_count=count,bounds=bounds,
        provided_normals='nx' in names,provided_colors='red' in names,protected_groups=groups,
        scope='whole point cloud; geometry transport and inspection; no inference or training qualification')
    return dict(metadata=metadata,properties=properties,point_count=count,columns={k:bytes(v) for k,v in columns.items()},points=points)


def inspect_archive(raw,expected_records=None):
    payloads=zip_payloads(raw);require('manifest.json' in payloads and len(payloads['manifest.json'])<=MAX_METADATA,'Bounded manifest')
    manifest=decode(payloads['manifest.json'])
    require(type(manifest)is dict and set(manifest)=={'schema_version','seed','split_report','coordinate_contract','limitations','records','protected_components','vocabulary'},'Full-proof canonical closed manifest')
    require(type(manifest['schema_version'])is int and manifest['schema_version']==1
        and type(manifest['seed'])is int and 0<=manifest['seed']<=2**32-1 and manifest['vocabulary']==[],'Canonical version/seed/no inferred vocabulary')
    require(type(manifest['coordinate_contract'])is str and type(manifest['limitations'])is list
        and all(type(v)is str for v in manifest['limitations']),'Declared canonical scope')
    rows=manifest['records'];require(type(rows)is list and 1<=len(rows)<=MAX_RECORDS,'Whole-cloud record cap')
    require(all(type(r)is dict and set(r)==ROW_KEYS for r in rows),'Closed whole-cloud records')
    ids=[r['id'] for r in rows];require(all(type(i)is str and ID.fullmatch(i) for i in ids) and len(set(ids))==len(ids),'Unique record IDs')
    if expected_records is not None:
        require(type(expected_records)is list and len(expected_records)==len(rows),'Expected full snapshot count')
        expected={r['id']:r for r in expected_records}
        require(set(expected)==set(ids),'Expected snapshot IDs')
        for row in rows:
            original=expected[row['id']]
            require(set(original) in (ROW_KEYS,ROW_KEYS-{'asset','asset_sha256','split','export_group'}),'Full expected owner/canonical snapshot keys')
            require(encoded(original)==encoded({k:row[k] for k in original}),'Exact expected full source snapshots')
    require(set(payloads)=={'manifest.json','README.txt'}|{split+'/'+name for split in SPLITS for name in ('records.jsonl','coco.json')}|{'assets/'+i+'.zip' for i in ids},'Exact canonical member closure')
    bundles=0;pairs={};oracles={}
    for row in rows:
        require(row['kind']=='pointcloud' and row['task']=='pointcloud_geometry' and row['review']=='human_reviewed'
            and row['source_available'] is row['source_lineage_known'] is True,'Available human-reviewed point source')
        integer(row['revision'],'Record revision');require(type(row['source_revision'])is int and row['source_revision']==1,'Immutable source revision')
        require(all(row[k] is None for k in ('text','pixel_hash','book_id','session_id','width','height','corner_annotation')),'Point source identity')
        strings(row['groups'],'Groups');strings(row['parents'],'Parents',True)
        require(type(row['annotation'])is dict and set(row['annotation'])=={'note'} and type(row['annotation']['note'])is str
            and 0<len(row['annotation']['note'])<=4000 and row['annotation']['note'].strip()==row['annotation']['note'],'Nonempty canonical human note')
        require(row['split'] in SPLITS and row['source_split'] in ('unassigned',*SPLITS),'Frozen split identity')
        asset='assets/'+row['id']+'.zip';bundle=payloads[asset];bundles+=len(bundle)
        require(row['asset']==asset and len(bundle)<=2*1024*1024+32*1024+1024 and bundles<=MAX_BUNDLES
            and sha(bundle)==row['asset_sha256']==row['content_hash']==row['source_sha256'],'Bounded complete bundle source hash')
        pair=zip_payloads(bundle,2,2*1024*1024+32*1024+1024)
        require(list(pair)==['points.ply','points.json'],'Exact ordered raw pair')
        oracle=raw_pair_oracle(pair['points.ply'],pair['points.json'])
        require(encoded(row['pointcloud'])==encoded(dict(oracle['metadata'],bundle_bytes=len(bundle))),'Exact independently reconstructed raw metadata/native groups')
        require(set(oracle['metadata']['protected_groups'])<=set(row['groups']),'All protected point groups')
        require(row['source_split']==oracle['metadata']['manifest']['lineage']['split']
            and (row['source_split']=='unassigned' or row['source_split']==row['split']),'Declared immutable fixed split')
        pairs[row['id']]=pair;oracles[row['id']]=oracle
    for split in SPLITS:
        stream=payloads[split+'/records.jsonl'];require(len(stream)<=MAX_METADATA and (not stream or stream.endswith(b'\n')),'Bounded complete JSONL')
        lines=stream.splitlines();require(len(lines)<=MAX_RECORDS and all(0<len(l)<=256*1024 for l in lines),'Bounded JSONL rows')
        require(encoded([decode(l) for l in lines])==encoded([r for r in rows if r['split']==split]),'Exact split JSONL records')
        coco=decode(payloads[split+'/coco.json']);require(len(payloads[split+'/coco.json'])<=4096
            and type(coco)is dict and set(coco)=={'info','licenses','images','annotations','categories'}
            and all(coco[k]==[] for k in ('licenses','images','annotations','categories')),'No geometry converted to COCO targets')
    proof=dict(manifest,assignments={r['id']:r['split'] for r in rows})
    family,context=graph_oracle(proof,rows);allocation_oracle(proof,family)
    require(all(r['export_group']==family[r['id']] for r in rows),'Exact selected export group')
    return dict(manifest=manifest,payloads=payloads,pairs=pairs,oracles=oracles,context=context,family_by_id=family)


def identity(path):
    raw=capture(path,MAX_PHYSICAL)
    return dict(path=str(path),bytes=len(raw),sha256=sha(raw))


def reader_pins():
    import numpy as np
    import plyfile
    pins=decode((ROOT/'tests/pointcloud-consumer-pins.json').read_bytes())
    require(np.__version__==pins['numpy'] and importlib.metadata.version('plyfile')==pins['plyfile']['version'],'Actual installed released reader versions')
    require(sha(Path(plyfile.__file__).read_bytes())==pins['plyfile']['module_sha256'],'Exact actual installed reader source hash')
    return np,plyfile,dict(pins,module=identity(Path(plyfile.__file__)))


def verify_fields(fields,oracle,np):
    require(type(fields)is dict and list(fields)==[p['name'] for p in oracle['properties']],'Separate original named native properties')
    reports=[]
    for prop in oracle['properties']:
        name=prop['name'];array=fields[name]
        require(isinstance(array,np.ndarray) and array.shape==(oracle['point_count'],)
            and array.dtype.str==DTYPES[prop['dtype']] and array.tobytes()==oracle['columns'][name],'Exact native shape/dtype/order/bits: '+name)
        reports.append(dict(name=name,shape=list(array.shape),dtype=array.dtype.str,native_sha256=sha(array.tobytes()),values=array.tolist() if len(array)<=8 else None))
    return reports


def actual_read(pair,oracle,folder,np,plyfile):
    folder.mkdir(parents=True,exist_ok=True)
    for name,raw in pair.items():(folder/name).write_bytes(raw)
    with (folder/'points.ply').open('rb') as stream:
        actual=plyfile.PlyData.read(stream,mmap=False)
    require([e.name for e in actual.elements]==['vertex'],'Actual external vertex-only read')
    vertices=actual['vertex'].data
    require(vertices.dtype.names==tuple(p['name'] for p in oracle['properties']),'Actual external exact property order')
    fields={name:vertices[name] for name in vertices.dtype.names}
    return dict(file=identity(folder/'points.ply'),sidecar=identity(folder/'points.json'),attributes=verify_fields(fields,oracle,np),status='PASS')


def analytic_originals(out,np,plyfile):
    from native_pointcloud_fixture import pair
    reports=[]
    for name in ('colored','xyz'):
        raw,sidecar=pair(name);oracle=raw_pair_oracle(raw,sidecar)
        if name=='colored':
            literal={'x':[-0.,1.,2.,.1],'y':[0.,2.,0.,2.],'z':[0.,0.,3.,1.],
                'nx':[0.]*4,'ny':[0.]*4,'nz':[2.]*4,'red':[255,0,0,127],'green':[0,255,0,128],'blue':[0,0,255,255]}
            require(oracle['columns']['x'][:4]==struct.pack('<I',0x80000000)
                and oracle['columns']['x'][-4:]==struct.pack('<I',0x3dcccccd),'Literal float32 signed zero and decimal bits')
        else:
            literal={'x':[10.,11.,11.],'y':[0.,1.,1.],'z':[-0.,2.,2.]}
            require(oracle['columns']['z'][:8]==struct.pack('<Q',0x8000000000000000),'Literal float64 signed zero bits')
        for prop in oracle['properties']:
            require(np.asarray(literal[prop['name']],dtype=DTYPES[prop['dtype']]).tobytes()==oracle['columns'][prop['name']],'Independent authored literal values, duplicate order, nonunit normals and RGB')
        reports.append(actual_read({'points.ply':raw,'points.json':sidecar},oracle,out/name,np,plyfile))
    return reports


def exercise(path,out,np,plyfile,expected=None):
    from native_pointcloud_dataset import NativePointCloudDataset,NativePointCloudError
    raw=capture(path,MAX_PHYSICAL);checked=inspect_archive(raw,expected)
    rows=checked['manifest']['records'];out.mkdir(parents=True,exist_ok=True)
    # This captured copy belongs to this fresh checker run, never the supplied owner archive.
    captured=out/'captured-release.zip';captured.write_bytes(raw)
    reads=[actual_read(checked['pairs'][r['id']],checked['oracles'][r['id']],out/'raw'/r['id'],np,plyfile) for r in rows]
    reports=[]
    context=[s for family in sorted(checked['manifest']['protected_components']) for s in checked['manifest']['protected_components'][family]]
    for split in SPLITS:
        dataset=NativePointCloudDataset(captured,sha256=sha(raw),split=split)
        selected=[r for r in rows if r['split']==split]
        require(len(dataset)==len(selected),'Whole cloud sample count for frozen explicit split')
        for index,row in enumerate(selected):
            sample=dataset[index];require(set(sample)=={'fields','metadata'},'Closed native sample')
            attributes=verify_fields(sample['fields'],checked['oracles'][row['id']],np)
            meta=sample['metadata']
            require(set(meta)=={'schema','release_sha256','split','array_axes','properties','record','declared_family_context','units','coordinate_system','attribute_semantics','consumer','limitations'},'Closed native sample metadata')
            require(meta['attribute_semantics']==dict(coordinates='xyz retain declared native units and frame',normals='dimensionless provided values; magnitude is retained',colors='raw unsigned eight-bit channels 0..255; no color space inferred'),'Explicit native attribute semantics without normalization or invented color space')
            require(meta['schema']=='native_pointcloud_sample_v1' and meta['release_sha256']==sha(raw) and meta['split']==split
                and meta['array_axes']==['point'] and encoded(meta['record'])==encoded(row),'Frozen exact record, release and named point axis')
            require(encoded(meta['declared_family_context'])==encoded(context),'Complete declared family context including unselected/deleted sources')
            require(meta['properties']==[{k:a[k] for k in ('name','shape','dtype')} for a in attributes],'Exact native descriptors')
            require(encoded(meta['coordinate_system'])==encoded(row['pointcloud']['manifest']['coordinate_system'])
                and meta['units']==row['pointcloud']['manifest']['units'],'Source units and frame retained')
            require(meta['consumer']==dict(plyfile='1.1.3',plyfile_module_sha256=sha(Path(plyfile.__file__).read_bytes()),numpy='2.5.3')
                and type(meta['limitations'])is list and len(meta['limitations'])>=len(checked['manifest']['limitations']),'Actual reader identity and explicit limitations')
            target=out/(split+'-'+str(index)+'.npz');target.write_bytes(b'previous output')
            dataset.write_npz(target,index=index)
            require(target.stat().st_size<=MAX_NPZ,'Complete NPZ physical bound')
            with np.load(target,allow_pickle=False) as saved:
                require(set(saved.files)==set(sample['fields'])|{'metadata_utf8'},'Closed pickle-free NPZ keys')
                verify_fields({k:saved[k] for k in sample['fields']},checked['oracles'][row['id']],np)
                require(saved['metadata_utf8'].dtype==np.dtype('uint8') and saved['metadata_utf8'].ndim==1
                    and encoded(decode(saved['metadata_utf8'].tobytes()))==encoded(meta),'UTF8 metadata bytes in NPZ')
            before=encoded(meta);sample['fields']['x'][0]=123;meta['record']['name']='caller mutation'
            fresh=dataset[index];verify_fields(fresh['fields'],checked['oracles'][row['id']],np)
            require(encoded(fresh['metadata'])==before,'Fresh arrays and deeply independent metadata')
            reports.append(dict(id=row['id'],split=split,index=index,attributes=attributes,npz=identity(target),metadata=fresh['metadata']))
        if not selected:
            sentinel=out/(split+'-empty.npz');sentinel.write_bytes(b'unchanged empty-split sentinel')
            try:dataset.write_npz(sentinel)
            except NativePointCloudError:pass
            else:raise ValueError('Empty split unexpectedly emitted a sample')
            require(sentinel.read_bytes()==b'unchanged empty-split sentinel','Empty split preserves previous output')
        try:dataset[True]
        except NativePointCloudError:pass
        else:raise ValueError('Boolean sample index accepted')
        if selected:
            before=captured.read_bytes()
            try:dataset.write_npz(captured)
            except NativePointCloudError:pass
            else:raise ValueError('Input release overwrite accepted')
            require(captured.read_bytes()==before,'Source release retained byte exactly')
    return dict(status='PASS',release=identity(path),records=len(rows),declared_context_members=len(context),
        families=len(checked['manifest']['protected_components']),actual_external_reads=reads,samples=reports),checked


def malformed_controls(raw,out):
    from native_pointcloud_dataset import NativePointCloudDataset,NativePointCloudError
    original=zip_payloads(raw);controls=[]
    for label in ('missing-proof','missing-context-parent','wrong-export-group','truncated-jsonl','asset-hash','duplicate-member'):
        values=dict(original);manifest=decode(values['manifest.json'])
        if label=='missing-proof':del manifest['protected_components']
        elif label=='missing-context-parent':
            for members in manifest['protected_components'].values():
                members[:]=[s for s in members if s['source_available']]
        elif label=='wrong-export-group':manifest['records'][0]['export_group']='component:'+'0'*64
        elif label=='asset-hash':manifest['records'][0]['asset_sha256']='0'*64
        elif label=='truncated-jsonl':
            name=next(s+'/records.jsonl' for s in SPLITS if values[s+'/records.jsonl'])
            values[name]=values[name][:-1]
        values['manifest.json']=encoded(manifest).encode()
        if label not in ('truncated-jsonl','duplicate-member'):
            for split in SPLITS:values[split+'/records.jsonl']=b''.join((encoded(r)+'\n').encode() for r in manifest['records'] if r['split']==split)
        damaged=archive_from(values,duplicate='manifest.json' if label=='duplicate-member' else None)
        path=out/(label+'.zip');path.write_bytes(damaged)
        try:inspect_archive(damaged)
        except ValueError:pass
        else:raise ValueError('Independent oracle accepted '+label)
        try:NativePointCloudDataset(path,sha256=sha(damaged),split='train')
        except NativePointCloudError as error:controls.append(dict(case=label,status='REFUSED',reason=str(error),artifact=identity(path)))
        else:raise ValueError('Production consumer accepted '+label)
    return controls


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--archive',type=Path)
    parser.add_argument('--expected',type=Path)
    args=parser.parse_args();out=output_preflight(args.output)
    sys.path.insert(0,str(ROOT));sys.path.insert(0,str(FIXTURES))
    np,plyfile,pins=reader_pins()
    from app import Dataset
    from native_pointcloud_fixture import populate,freeze,admit,review
    expected=decode(capture(args.expected,MAX_METADATA)) if args.expected else None
    if type(expected)is dict:expected=expected['records']
    bridge=None
    if args.archive:path=args.archive
    else:
        first=Dataset(str(out/'owner-first'))
        try:
            rows,bridge=populate(first);raw,preview=freeze(first,rows)
            path=out/'first-release.zip';path.write_bytes(raw);expected=rows
        finally:first.close()
    result=dict(status='PASS',scope='Existing canonical whole point clouds, actual pinned native arrays and atomic pickle-free derived NPZ; no model, training or geometric qualification.',
        role='Checker authored independently of root-owned production consumer; independent archive/native oracles followed by actual production API execution.',
        pins=pins,analytic_originals=analytic_originals(out/'analytic-originals',np,plyfile),
        consumer_limits=dict(records=64,release_physical_and_logical_bytes=MAX_PHYSICAL,metadata_bytes=MAX_METADATA,context_members=5000,selected_bundles_bytes=MAX_BUNDLES,npz_bytes=MAX_NPZ))
    result['first'],checked=exercise(path,out/'first',np,plyfile,expected)
    first_raw=capture(path,MAX_PHYSICAL);first_rows=checked['manifest']['records']
    second=Dataset(str(out/'owner-second'));transfer=[]
    try:
        rows=[]
        for original in first_rows:
            rawpair=checked['pairs'][original['id']]
            row=admit(second.workbench,rawpair['points.ply'],rawpair['points.json'])
            require(row['id'] not in {r['id'] for r in first_rows} and row['review']=='draft' and row['annotation'] is None
                and row['provenance']['rights']=='unknown' and row['parents']==[],'Second owner new local draft, unknown rights and no inherited human review/parents')
            require(encoded(row['pointcloud'])==encoded(original['pointcloud']) and row['source_split']==original['source_split'],'Immutable native source metadata and fixed split retained')
            require(second.workbench.asset(row['id'])[0]==checked['payloads'][original['asset']],'Whole exact source bundle bytes')
            rows.append(row);transfer.append(dict(original_id=original['id'],new_id=row['id'],admitted=copy.deepcopy(row)))
        require(len({r['id'] for r in rows})==len(rows),'Unique disjoint second-owner IDs')
        request=dict(items=[{k:r[k] for k in ('id','revision','source_revision')} for r in rows],ratios=dict(train=50,validation=50,test=0),seed=87)
        require(not second.releases.preview(request)['eligible'],'Draft second-owner exports remain ineligible')
        rows=[review(second.workbench,r,'draft') for r in rows]
        rows=[second.workbench.get(r['id']) for r in rows]
        require(all(r['review']=='draft' for r in rows),'Saved draft note and actual reopened owner records')
        for proof,row in zip(transfer,rows):proof['reopened_draft']=copy.deepcopy(row)
        rows=[review(second.workbench,r) for r in rows]
        raw,preview=freeze(second,rows);second_path=out/'second-release.zip';second_path.write_bytes(raw)
        result['second'],other=exercise(second_path,out/'second',np,plyfile,rows)
        for proof,row in zip(transfer,rows):
            proof['reviewed']=copy.deepcopy(row)
            require(other['pairs'][row['id']]==checked['pairs'][proof['original_id']],'Byte-exact raw pair frozen reexport')
    finally:second.close()
    require(capture(path,MAX_PHYSICAL)==first_raw,'Original owner release never mutated')
    result['transfer']=dict(records=transfer,byte_exact_raw_pairs=True,whole_declared_families=True,preserved_sidecar_fixed_splits=True,
        caveat='Raw pairs preserve sidecar lineage but do not transfer sender-local IDs, parents, arbitrary groups, assignments, rights notes or human annotations/review.')
    if bridge is not None:
        require(len(checked['context'])==4 and len(other['context'])==3 and bridge['id'] in checked['context'],'Known deleted first-owner parent retained only in its complete first-owner proof')
        result['known_deleted_parent']=bridge
        result['malformed_controls']=malformed_controls(first_raw,out)
    else:result['malformed_controls']=[]
    result['records']=result['first']['records'];result['declared_context_members']=result['first']['declared_context_members']
    result['release_sha256']=sha(first_raw);result['samples']=result['first']['samples']
    (out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print('Native whole point-cloud dataset, actual pinned reader, NPZ and second-owner roundtrip PASS: '+str(out))


if __name__=='__main__':main()
