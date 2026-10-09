"""Separate bounded binary-mesh profile. No optional numerical dependency."""
from array import array
from decimal import Decimal
from fractions import Fraction
import hashlib
import io
import json
import math
import re
import stat
import struct
import zipfile

FORMAT = 'tuldok_mesh_binary_v1'
VERTICES = 50_000
TRIANGLES = 100_000
PLY_BYTES = 4 * 1024 * 1024
HEADER_BYTES = 64 * 1024
MANIFEST_BYTES = 32 * 1024
REQUEST_BYTES = 32 * 1024
RESPONSE_BYTES = 8 * 1024 * 1024
BUNDLE_BYTES = 12 * 1024 * 1024
RESULT_BYTES = 256 * 1024
WORKER_AS_BYTES = 256 * 1024 * 1024
WORKER_CPU_SECONDS = 30
WORKER_WALL_SECONDS = 45
SOURCE_COMMIT = '136f4947c7ef9bd2d4fe5cff09086489b0cb501d'
SOURCE_REPOSITORY = 'https://github.com/MrScripty/Kenoma'
SOURCE_WASM_SHA256 = 'da3958056caeda3d190dfff7cb708657fb81c8389f953ad4c022a26e64bcdf8f'
HASH = re.compile(r'^[a-f0-9]{64}$')
INTEGER = re.compile(r'^(?:0|[1-9][0-9]*)$')
PROPERTIES = (['x', 'y', 'z'], ['x', 'y', 'z', 'nx', 'ny', 'nz'])
LINKS = [(0,1),(1,2),(2,3),(1,4),(4,5),(5,6),(1,7),(7,8),(8,9),
         (0,10),(10,11),(11,12),(0,13),(13,14),(14,15)]
# Exact pinned human_core/src/samples.rs constructor, not an observed mesh fixture.
REST_POINTS = [(0,.95,0,.16),(0,1.35,0,.21),(0,1.55,0,.07),(0,1.72,0,.13),
    (.32,1.4,0,.085),(.58,1.2,0,.065),(.79,1,0,.055),
    (-.32,1.4,0,.085),(-.58,1.2,0,.065),(-.79,1,0,.055),
    (.15,.85,0,.10),(.15,.48,0,.075),(.15,.08,.08,.065),
    (-.15,.85,0,.10),(-.15,.48,0,.075),(-.15,.08,.08,.065)]


class BinaryMeshError(ValueError):
    pass


class SourceFloat(float):
    """Retain exact JSON spelling for direct decimal-to-f32 verification."""
    __slots__ = ('token',)
    def __new__(cls, token):
        value = super().__new__(cls, token)
        value.token = token
        return value


def require(condition, message):
    if not condition:
        raise BinaryMeshError('Invalid bounded binary mesh: ' + message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def exact(value, keys, name):
    require(type(value) is dict and set(value) == set(keys), name + ' fields mismatch')


def integer(value, low, high, name):
    require(type(value) is int and low <= value <= high, name + ' outside bounds')


def strict_json(raw, cap):
    require(0 < len(raw) <= cap, 'JSON byte cap exceeded')
    quoted, escaped, depth = False, False, 0
    for byte in raw:
        if quoted:
            if escaped: escaped = False
            elif byte == 92: escaped = True
            elif byte == 34: quoted = False
        elif byte == 34: quoted = True
        elif byte in (91,123):
            depth += 1
            require(depth <= 64, 'JSON depth exceeds64')
        elif byte in (93,125): depth -= 1
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    def number(token):
        value = float(token)
        require(math.isfinite(value) and (value != 0 or Decimal(token) == 0), 'nonfinite or underflow JSON number')
        return SourceFloat(token)
    def constant(_):
        raise BinaryMeshError('Invalid bounded binary mesh: nonfinite JSON constant')
    def whole(token):
        require(token != '-0', 'integer negative-zero spelling refused; use explicit IEEE float zero')
        return int(token)
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_float=number, parse_int=whole, parse_constant=constant)
    def unicode_check(item):
        if isinstance(item, str):
            require(not any(0xD800 <= ord(c) <= 0xDFFF for c in item), 'invalid Unicode')
        elif isinstance(item, dict):
            for key, child in item.items(): unicode_check(key); unicode_check(child)
        elif isinstance(item, list):
            for child in item: unicode_check(child)
    unicode_check(value)
    return value


def preflight_zip(raw, maximum_entries, logical_cap):
    """Stdlib-only central preflight, matching retained native consumer rules."""
    require(0 < len(raw) <= BUNDLE_BYTES, 'bundle physical cap exceeded')
    require(len(raw)>=22 and raw[-22:-18]==b'PK\x05\x06','exact ZIP end without comments/trailing bytes required')
    _,disk,cd_disk,on_disk,count,size,offset,comment=struct.unpack_from('<4s4H2IH',raw,len(raw)-22)
    require(disk==cd_disk==comment==0 and on_disk==count and 0<count<=maximum_entries,'bounded single-disk ZIP count required')
    require(size<=maximum_entries*512 and offset+size==len(raw)-22,'exact bounded central directory required')
    cursor,names,total=offset,set(),0
    for _ in range(count):
        require(cursor+46<=offset+size,'truncated central directory')
        fields=struct.unpack_from('<4s6H3I5H2I',raw,cursor)
        require(fields[0]==b'PK\x01\x02' and fields[2]<45 and fields[13]==0 and fields[16]!=0xffffffff
            and fields[11]==fields[12]==0,'ZIP64/extras/multidisk entries refused')
        require(fields[4]==0 and fields[3] in (0,0x800) and fields[8]==fields[9], 'unencrypted stored ZIP required')
        require(stat.S_IFMT(fields[15]>>16) in (0,stat.S_IFREG) and not fields[15]&0x10,'regular ZIP members required')
        end=cursor+46+fields[10]
        require(0<fields[10]<=120 and end<=offset+size,'bounded ZIP names required')
        name=raw[cursor+46:end].decode('ascii')
        require(name not in names and not name.startswith('/') and '\\' not in name
            and all(x not in ('','.','..') for x in name.split('/')),'unique safe ZIP members required')
        names.add(name);total+=fields[9];require(total<=logical_cap,'ZIP logical cap exceeded');cursor=end
    require(cursor==offset+size,'central directory count mismatch')
    archive = zipfile.ZipFile(io.BytesIO(raw))
    require(len(archive.infolist())==count and set(archive.namelist())==names,'ZIP directory mismatch')
    return archive


def stored_zip(raw, names, caps):
    archive = preflight_zip(raw,len(names),min(sum(caps),BUNDLE_BYTES))
    try:
        require(archive.namelist() == names and len(set(names)) == len(names), 'ordered source members mismatch')
        cursor, total = 0, 0
        for info, cap in zip(archive.infolist(), caps):
            require(info.compress_type == zipfile.ZIP_STORED and 0 < info.file_size <= cap
                and info.compress_size == info.file_size and info.flag_bits in (0,0x800)
                and not info.extra and not info.comment and (info.external_attr >> 16) & 0o170000 != 0o120000,
                'bounded stored regular members without extras required')
            require(info.header_offset == cursor and cursor + 30 <= len(raw), 'contiguous ZIP local headers required')
            fields = struct.unpack_from('<4s5H3I2H', raw, cursor)
            require(fields[0] == b'PK\x03\x04' and fields[1] < 45 and fields[2] == info.flag_bits
                and fields[3] == 0 and fields[6] == info.CRC and fields[7] == fields[8] == info.file_size
                and fields[10] == 0 and raw[cursor+30:cursor+30+fields[9]] == info.filename.encode('ascii'),
                'ZIP local/central association mismatch')
            cursor += 30 + fields[9] + info.file_size
            total += info.file_size
        require(total <= BUNDLE_BYTES and cursor == archive.start_dir, 'ZIP logical cap or directory boundary mismatch')
        return archive
    except BaseException:
        archive.close()
        raise


def scalar(value, name):
    require(type(value) in (int,float,SourceFloat) and math.isfinite(value) and abs(value) <= 1e12, name + ' nonfinite or magnitude exceeded')
    return float(value)


def f32(value):
    # The source API's numbers are f32 shortest-roundtrip decimals. Exact-neighbor
    # correction also rejects crafted decimal double-rounding substitutions.
    token = getattr(value, 'token', repr(value))
    value = scalar(value, 'source scalar')
    bits = struct.unpack('<I', struct.pack('<f', abs(value)))[0]
    exact_value = Fraction(Decimal(token).copy_abs())
    def binary(word): return struct.unpack('<f', struct.pack('<I', word))[0]
    center = Fraction.from_float(binary(bits))
    if bits:
        midpoint = (Fraction.from_float(binary(bits-1)) + center) / 2
        if exact_value < midpoint or exact_value == midpoint and bits % 2: bits -= 1
    upper = (Fraction.from_float(binary(bits+1)) + Fraction.from_float(binary(bits))) / 2
    if exact_value > upper or exact_value == upper and bits % 2: bits += 1
    rounded = math.copysign(binary(bits), value)
    require(value == 0 or rounded != 0, 'source f32 underflow')
    return rounded


def parse_ply(raw):
    require(0 < len(raw) <= PLY_BYTES, 'binary PLY byte cap exceeded')
    stream = io.BytesIO(raw)
    header = []
    while True:
        line = stream.readline(HEADER_BYTES + 1)
        require(line and len(line) <= HEADER_BYTES and stream.tell() <= HEADER_BYTES, 'binary header cap/truncation')
        require(line.endswith(b'\n') and b'\r' not in line.replace(b'\r\n',b''), 'binary header LF/CRLF required')
        require(not any(x < 32 and x not in (9,10,13) for x in line), 'header controls refused')
        text = line.decode('ascii').rstrip('\r\n')
        if text == 'end_header': break
        header.append(text)
    require(header[:2] == ['ply','format binary_little_endian 1.0'], 'little-endian binary PLY1.0 required')
    grammar = [x.split() for x in header[2:] if not x.startswith('comment ')]
    require(grammar and len(grammar[0]) == 3 and grammar[0][:2] == ['element','vertex'] and INTEGER.fullmatch(grammar[0][2]), 'vertex element required')
    n = int(grammar[0][2]); integer(n,1,VERTICES,'vertex count')
    props, cursor = [], 1
    while cursor < len(grammar) and grammar[cursor][:1] == ['property']:
        item = grammar[cursor]
        require(len(item) == 3 and item[1] in ('float','double'), 'vertex dtype mismatch')
        props.append({'name':item[2],'dtype':item[1]}); cursor += 1
    require([p['name'] for p in props] in PROPERTIES, 'xyz/complete normal axes required')
    require(cursor < len(grammar) and len(grammar[cursor]) == 3 and grammar[cursor][:2] == ['element','face']
        and INTEGER.fullmatch(grammar[cursor][2]), 'face element required')
    count = int(grammar[cursor][2]); integer(count,1,TRIANGLES,'triangle count')
    require(len(grammar) == cursor+2 and grammar[cursor+1] in
        (['property','list','uchar','int','vertex_indices'],['property','list','uchar','uint','vertex_indices']), 'triangle list dtype mismatch')
    face_type = grammar[cursor+1][3]
    vertex = struct.Struct('<'+''.join('f' if p['dtype']=='float' else 'd' for p in props))
    face = struct.Struct('<B'+('iii' if face_type=='int' else 'III'))
    offset = stream.tell()
    require(len(raw) == offset + n*vertex.size + count*face.size, 'binary body truncated/trailing')
    columns = [array('f' if p['dtype']=='float' else 'd') for p in props]
    low, high = [math.inf]*3, [-math.inf]*3
    view = memoryview(raw)
    for values in vertex.iter_unpack(view[offset:offset+n*vertex.size]):
        for i,value in enumerate(values):
            scalar(value,'binary scalar'); columns[i].append(value)
        for i in range(3): low[i]=min(low[i],values[i]); high[i]=max(high[i],values[i])
    faces, unique = array('i' if face_type=='int' else 'I'), set()
    for items in face.iter_unpack(view[offset+n*vertex.size:]):
        require(items[0] == 3, 'triangle list length must be3')
        indices = items[1:]
        require(len(set(indices)) == 3 and all(0 <= index < n for index in indices), 'triangle indices distinct/in bounds required')
        a,b,c = sorted(indices); key=(a<<32)|(b<<16)|c
        require(key not in unique, 'duplicate unordered face across whole mesh'); unique.add(key)
        a,b,c = indices
        u=[columns[i][b]-columns[i][a] for i in range(3)]
        v=[columns[i][c]-columns[i][a] for i in range(3)]
        cross=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        require(any(value != 0 for value in cross), 'triangle zero representable cross product')
        faces.extend(indices)
    return {'properties':props,'columns':columns,'faces':faces,'face_type':face_type,
        'vertex_count':n,'triangle_count':count,'bounds':{'min':low,'max':high},'offset':offset}


def family_hash(geometry, units, frame):
    # Identical bytes to existing mesh encode({...}), without its giant list/JSON.
    digest = hashlib.sha256()
    def write(text): digest.update(text.encode('utf-8'))
    write('{"coordinate_system":'+encode(frame)+',"faces":[')
    for index in range(geometry['triangle_count']):
        if index: write(',')
        write(encode(list(geometry['faces'][index*3:index*3+3])))
    write('],"units":'+encode(units)+',"vertices":[')
    for index in range(geometry['vertex_count']):
        if index: write(',')
        write(encode([0.0 if c[index] == 0 else c[index] for c in geometry['columns'][:3]]))
    write(']}')
    return digest.hexdigest()


def descriptor(raw):
    return {'bytes':len(raw),'sha256':sha(raw)}


def validate_descriptor(value, raw):
    exact(value,('bytes','sha256'),'source descriptor')
    require(type(value['bytes']) is int and value['bytes']==len(raw) and value['sha256']==sha(raw), 'source hash/byte association mismatch')


def manifest(raw, binary):
    value = strict_json(raw,MANIFEST_BYTES)
    exact(value,('format','geometry_file','geometry_bytes','geometry_sha256','units','coordinate_system','provenance','source'),'manifest')
    require(value['format']==FORMAT and value['geometry_file']=='mesh.ply', 'explicit binary profile required')
    require(type(value['geometry_bytes']) is int and value['geometry_bytes']==len(binary)
        and value['geometry_sha256']==sha(binary), 'geometry hash/byte association mismatch')
    require(value['units'] in ('m','cm','mm'), 'units mismatch')
    frame=value['coordinate_system']; exact(frame,('frame','handedness','up_axis'),'frame')
    require(type(frame['frame']) is str and 0<len(frame['frame'])<=120 and frame['frame'].strip()
        and frame['handedness'] in ('right','left') and frame['up_axis'] in ('x','y','z'), 'coordinate frame mismatch')
    exact(value['provenance'],('source','revision','license','description'),'provenance')
    require(all(type(x) is str and x.strip() and len(x)<=1000 for x in value['provenance'].values()), 'provenance text mismatch')
    exact(value['source'],('kind','files'),'source')
    return value


def source_legacy(files, geometry, sidecar):
    import meshes  # Existing Pillow-only application dependency; no NumPy.
    with stored_zip(files['source.zip'],['mesh.ply','mesh.json'],[meshes.PLY_LIMIT,meshes.MANIFEST_LIMIT]) as archive:
        original=meshes.prepare(archive.read('mesh.ply'),archive.read('mesh.json'))
    parsed=original['geometry']; original_manifest=original['metadata']['manifest']
    require(geometry['properties']==parsed['properties'] and geometry['face_type']=='int'
        and geometry['vertex_count']==len(parsed['vertices']) and geometry['triangle_count']==len(parsed['faces']), 'original native layout mismatch')
    for name in ('units','coordinate_system','provenance'):
        require(sidecar[name]==original_manifest[name], 'original source '+name+' mismatch')
    for index,row in enumerate(parsed['vertices']):
        for col,prop in enumerate(parsed['properties']):
            dtype='<f' if prop['dtype']=='float' else '<d'
            require(struct.pack(dtype,row[col])==struct.pack(dtype,geometry['columns'][col][index]), 'original native property bits mismatch')
    require(all(list(geometry['faces'][i*3:i*3+3])==row for i,row in enumerate(parsed['faces'])), 'original ordered topology mismatch')
    return original['metadata']['protected_groups'], {'kind':'tuldok_mesh_v1','original_manifest':original_manifest,
        'native_zero':'existing source decoder canonical positive zero'}


def rest_graph():
    return {'nodes':[{'position':[f32(x),f32(y),f32(z)],'radii':[f32(r),f32(r)],'root':i==0}
        for i,(x,y,z,r) in enumerate(REST_POINTS)],'edges':[{'a':a,'b':b} for a,b in LINKS]}


def source_kenoma(files, geometry, sidecar):
    request=strict_json(files['request.json'],REQUEST_BYTES)
    response=strict_json(files['response.json'],RESPONSE_BYTES)
    producer=strict_json(files['producer.json'],MANIFEST_BYTES)
    exact(request,('version','operation'),'bind request')
    require(type(request['version']) is int and request['version']==1,'request version mismatch')
    operation=request['operation'];require(type(operation) is dict and set(operation) in
        ({'type','rig_version'},{'type','rig_version','surface_options'}),'bind operation fields mismatch')
    require(operation['type']=='rig_bind' and type(operation['rig_version']) is int and operation['rig_version']==1,'neutral rig-bind operation required')
    cell=f32(.016)
    if 'surface_options' in operation:
        exact(operation['surface_options'],('cell_size',),'surface options');cell=f32(operation['surface_options']['cell_size'])
    require(f32(.008) <= cell <= f32(.04),'source cell size outside supported range')
    exact(response,('version','ok','rig_version','rig_id','graph','head','options','mesh'),'bind response')
    for key in ('version','rig_version'): integer(response[key],1,1,key)
    require(response['ok'] is True,'successful bind response required');integer(response['rig_id'],1,2**32-1,'transient rig id')
    exact(response['head'],('yaw','pitch'),'head');require(all(type(x) in (int,float,SourceFloat) and x==0 for x in response['head'].values()),'neutral head required')
    require(response['options']=={'ring_sides':8,'target_segment_length_factor':1.25,'max_edge_segments':64},'legacy options mismatch')
    graph=response['graph'];exact(graph,('nodes','edges'),'rest graph')
    require(type(graph['nodes']) is list and len(graph['nodes'])==16 and graph['edges']==[{'a':a,'b':b} for a,b in LINKS],'canonical graph required')
    for edge in graph['edges']:
        exact(edge,('a','b'),'edge')
        integer(edge['a'],0,15,'edge a');integer(edge['b'],0,15,'edge b')
    normalized={'nodes':[],'edges':graph['edges']}
    for node in graph['nodes']:
        exact(node,('position','radii','root'),'node')
        require(type(node['position']) is list and len(node['position'])==3 and type(node['radii']) is list and len(node['radii'])==2 and type(node['root']) is bool,'node shape mismatch')
        normalized['nodes'].append({'position':[f32(x) for x in node['position']], 'radii':[f32(x) for x in node['radii']], 'root':node['root']})
    expected_graph=rest_graph()
    # Pinned human_surface/src/lib.rs field(): native f32 radius resolution.
    factor=f32(.7)
    require(all(cell<=struct.unpack('<f',struct.pack('<f',min(node['radii'])*factor))[0]
        for node in expected_graph['nodes']), 'source cell size exceeds pinned radius resolution')
    require(normalized==expected_graph,'pinned canonical rest graph mismatch')
    for node,expected in zip(normalized['nodes'],expected_graph['nodes']):
        require(all(struct.pack('<f',a)==struct.pack('<f',b) for a,b in zip(node['position']+node['radii'],expected['position']+expected['radii'])),
            'pinned rest graph native bits mismatch')
    require(geometry['properties']==[{'name':x,'dtype':'float'} for x in PROPERTIES[1]] and geometry['face_type']=='uint','Kenoma native f32/u32 layout required')
    mesh=response['mesh'];exact(mesh,('positions','normals','indices','source_nodes','source_edges','diagnostics'),'source mesh')
    n=geometry['vertex_count'];t=geometry['triangle_count']
    for key,offset in (('positions',0),('normals',3)):
        require(type(mesh[key]) is list and len(mesh[key])==n,'source vertex count mismatch')
        for index,row in enumerate(mesh[key]):
            require(type(row) is list and len(row)==3,'source XYZ shape mismatch')
            for col,value in enumerate(row):
                require(struct.pack('<f',f32(value))==struct.pack('<f',geometry['columns'][offset+col][index]),'source native f32 bits mismatch')
    require(type(mesh['indices']) is list and len(mesh['indices'])==t*3,'source triangle count mismatch')
    for original,observed in zip(mesh['indices'],geometry['faces']):
        integer(original,0,n-1,'source index');require(original==observed,'source ordered triangle mismatch')
    for key,maximum in (('source_nodes',15),('source_edges',14)):
        require(type(mesh[key]) is list and len(mesh[key])==n,'source association count mismatch')
        for value in mesh[key]:
            if value is not None: integer(value,0,maximum,'sparse source association')
    require(mesh['diagnostics']==[],'neutral canonical diagnostics must be empty')
    require(sidecar['units']=='m' and sidecar['coordinate_system']=={'frame':'character-local','handedness':'right','up_axis':'y'},'source model frame mismatch')
    exact(producer,('fixture_version','provenance','source_commit','compatible_editor_checkpoint','protocol_version','rig_version',
        'crate_version','wasm','coordinate_frame','request','response','counts','bounds','options','note'),'producer manifest')
    for key in ('fixture_version','protocol_version','rig_version'):integer(producer[key],1,1,'producer '+key)
    require(producer['source_commit']==SOURCE_COMMIT and producer['crate_version']=='0.1.0','producer source pins mismatch')
    for key,name in (('request','request.json'),('response','response.json')):
        info=producer.get(key);require(type(info) is dict and info.get('file')==name and info.get('bytes')==len(files[name]) and info.get('sha256')==sha(files[name]),'producer '+key+' association mismatch')
    wasm=producer.get('wasm');exact(wasm,('bytes','sha256'),'producer WASM')
    require(type(wasm['bytes']) is int and wasm['bytes']==471190 and wasm['sha256']==SOURCE_WASM_SHA256,'pinned producer WASM claim mismatch')
    require(producer['coordinate_frame']=={'handedness':'right-handed','up':'+Y','head_forward':'+Z','length_unit':'metre',
        'angle_unit':'radian','space':'character-local; no scene placement transform','triangle_winding':'counterclockwise viewed from outside'},'producer frame claim mismatch')
    counts={'source_nodes':16,'source_edges':15,'positions':n,'normals':n,'triangle_indices':t*3,'triangles':t}
    exact(producer['counts'],counts,'producer counts')
    require(all(type(producer['counts'][key]) is int and producer['counts'][key]==value for key,value in counts.items()),'producer count association mismatch')
    exact(producer['bounds'],('min','max'),'producer bounds')
    for key in ('min','max'):
        require(type(producer['bounds'][key]) is list and len(producer['bounds'][key])==3
            and [f32(x) for x in producer['bounds'][key]]==geometry['bounds'][key],'producer bounds association mismatch')
    exact(producer['options'],('cell_size','head'),'producer options')
    exact(producer['options']['head'],('yaw','pitch'),'producer head')
    require(all(type(x) in (int,float,SourceFloat) and x==0 for x in producer['options']['head'].values()),'typed neutral producer head required')
    require(f32(producer['options']['cell_size'])==cell and producer['options']['head']==response['head'],'producer binding options association mismatch')
    require(type(producer.get('provenance')) is str and producer['provenance'].strip(),'producer provenance required')
    require(sidecar['provenance']['source']==SOURCE_REPOSITORY and sidecar['provenance']['revision']==SOURCE_COMMIT,'declared Kenoma source mismatch')
    binding={'source_commit':SOURCE_COMMIT,'rig_version':1,'cell_size':cell,'rest_graph':expected_graph}
    return ['kenoma-binding:'+sha(encode(binding).encode())], {'kind':'kenoma_rig_bind_v1','binding':binding,
        'producer':producer,'transport_claims':'Retained compressed-file and generation claims; consumer verifies exact uncompressed request/response and pinned WASM declaration, not generation authenticity.',
        'transient_rig_id':response['rig_id'],'head':response['head'],
        'options':response['options'],'sparse_associations':{'source_nodes':n,'source_edges':n},
        'native_zero':'binary source IEEE signed-zero bits retained; family alone canonicalizes zero'}


def validate_bundle(raw):
    # Central preflight BEFORE reading any large member.
    require(0<len(raw)<=BUNDLE_BYTES,'bundle cap exceeded')
    with preflight_zip(raw,5,BUNDLE_BYTES) as header:
        require('mesh.json' in header.namelist() and header.getinfo('mesh.json').file_size<=MANIFEST_BYTES,'bounded manifest required')
        sidecar_raw=header.read('mesh.json')
    preliminary=strict_json(sidecar_raw,MANIFEST_BYTES)
    require(type(preliminary) is dict and type(preliminary.get('source')) is dict,'source manifest required')
    kind=preliminary['source'].get('kind')
    if kind=='tuldok_mesh_v1':
        source_names=['source.zip'];source_caps=[2*1024*1024+32*1024+1024]
    elif kind=='kenoma_rig_bind_v1':
        source_names=['request.json','response.json','producer.json'];source_caps=[REQUEST_BYTES,RESPONSE_BYTES,MANIFEST_BYTES]
    else: raise BinaryMeshError('Invalid bounded binary mesh: unsupported source kind')
    with stored_zip(raw,['mesh.ply','mesh.json']+source_names,[PLY_BYTES,MANIFEST_BYTES]+source_caps) as archive:
        binary=archive.read('mesh.ply');sidecar=manifest(sidecar_raw,binary)
        exact(sidecar['source']['files'],source_names,'source files')
        files={name:archive.read(name) for name in source_names}
        for name in source_names:validate_descriptor(sidecar['source']['files'][name],files[name])
    geometry=parse_ply(binary)
    groups,evidence=(source_legacy if kind=='tuldok_mesh_v1' else source_kenoma)(files,geometry,sidecar)
    family=family_hash(geometry,sidecar['units'],sidecar['coordinate_system'])
    groups=list(dict.fromkeys(groups+['mesh-source:'+sha(binary),'mesh-family:'+family]))
    metadata={'manifest':sidecar,'manifest_sha256':sha(sidecar_raw),'properties':geometry['properties'],
        'vertex_count':geometry['vertex_count'],'triangle_count':geometry['triangle_count'],'bounds':geometry['bounds'],
        'provided_normals':len(geometry['properties'])==6,'protected_groups':groups,
        'topology_dtype':'<i4' if geometry['face_type']=='int' else '<u4','source_evidence':evidence,
        'resource_profile':FORMAT,'scope':'whole static mesh; exact source-bound geometry transport and inspection; no physics or training qualification'}
    triangles=[]
    for i in range(min(512,geometry['triangle_count'])):
        triangles.append([[geometry['columns'][axis][j] for axis in range(3)] for j in geometry['faces'][i*3:i*3+3]])
    return {'metadata':metadata,'triangles':triangles,'bundle_sha256':sha(raw),'bundle_bytes':len(raw)}


def write_bundle(binary, source_files, source_kind, base):
    sidecar=dict(base,format=FORMAT,geometry_file='mesh.ply',geometry_bytes=len(binary),geometry_sha256=sha(binary),
        source={'kind':source_kind,'files':{name:descriptor(raw) for name,raw in source_files.items()}})
    sidecar_raw=encode(sidecar).encode();require(len(sidecar_raw)<=MANIFEST_BYTES,'manifest cap exceeded')
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_STORED) as archive:
        for name,raw in [('mesh.ply',binary),('mesh.json',sidecar_raw)]+list(source_files.items()):archive.writestr(zipfile.ZipInfo(name),raw)
    raw=output.getvalue();require(len(raw)<=BUNDLE_BYTES,'complete bundle cap exceeded')
    return raw


def binary_from_rows(properties, vertices, faces, face_type, comments=()):
    header=['ply','format binary_little_endian 1.0']+['comment '+x for x in comments]
    header+=['element vertex '+str(len(vertices))]+['property '+p['dtype']+' '+p['name'] for p in properties]
    header+=['element face '+str(len(faces)),'property list uchar '+face_type+' vertex_indices','end_header']
    raw_header=('\n'.join(header)+'\n').encode('ascii');require(len(raw_header)<=HEADER_BYTES,'header cap exceeded')
    v=struct.Struct('<'+''.join('f' if p['dtype']=='float' else 'd' for p in properties));f=struct.Struct('<B'+('iii' if face_type=='int' else 'III'))
    require(len(raw_header)+v.size*len(vertices)+f.size*len(faces)<=PLY_BYTES,'binary cap exceeded')
    stream=io.BytesIO();stream.write(raw_header)
    for row in vertices:stream.write(v.pack(*row))
    for row in faces:stream.write(f.pack(3,*row))
    return stream.getvalue()
