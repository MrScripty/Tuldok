"""Explicit offline CPU-runtime capture; immutable filesystem content is canonical."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import uuid

from access import Access, AccessError, authorized
from workbench import WorkbenchError, encode

PROFILE = 'captured_cpu_python_v1'
MAX_FILES = 40000
MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_BYTES = 2 * 1024 * 1024 * 1024
MAX_MANIFEST = 16 * 1024 * 1024
SYSTEM_LIB = Path('/usr/lib/x86_64-linux-gnu')
DEFAULT_RESERVE = 6 * 1024 * 1024 * 1024
NAME = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.+-]{0,159}')
HASH = re.compile(r'[a-f0-9]{64}')


def fail(message, code='invalid'):
    raise WorkbenchError('CPU runtime: ' + message, code, 409 if code in ('conflict','unavailable','stale') else 400)


def canonical(value):
    from recipe_process import encoded
    return encoded(value)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def configuration(value):
    required = {'schema_version','python_root','python_version','site_packages','packages'}
    if type(value) is not dict or set(value) - {'exclude_paths','stdlib_exclude_paths'} != required or type(value['schema_version']) is not int or value['schema_version'] != 1:
        fail('Use the closed version-1 explicit source configuration.')
    if type(value['python_version']) is not str or not re.fullmatch(r'3\.\d+', value['python_version']):
        fail('Python version must name a specific Python 3 minor version.')
    for name in ('python_root','site_packages'):
        if type(value[name]) is not str or not Path(value[name]).is_absolute(): fail('Source roots must be explicit absolute directories.')
        if not Path(value[name]).is_dir(): fail('Configured source directory is unavailable.','unavailable')
    packages=value['packages']
    if type(packages) is not list or not 1 <= len(packages) <= 128 or any(type(x) is not str or not NAME.fullmatch(x) for x in packages) or len(set(packages)) != len(packages):
        fail('Choose 1–128 unique explicit package entries.')
    if not {'torch','numpy'} <= set(packages): fail('The CPU profile requires explicit Torch and NumPy packages.')
    if any(name.endswith('.pth') for name in packages): fail('Automatic .pth hooks cannot be selected.')
    excluded=value.get('exclude_paths',[])
    if type(excluded) is not list or len(excluded)>32 or any(type(item) is not str or item.startswith('/') or any(part in ('','.', '..') for part in item.split('/')) or item.split('/')[0] not in packages or '.dist-info' in item or 'license' in item.lower() for item in excluded):
        fail('Exclusions must be bounded explicit paths inside selected non-metadata packages.')
    excluded=value.get('stdlib_exclude_paths',[])
    if type(excluded) is not list or len(excluded)>32 or any(type(item) is not str or not item.startswith('lib-dynload/') or len(item.split('/'))!=2 or not NAME.fullmatch(item.split('/')[1]) or not item.endswith('.so') for item in excluded):
        fail('Stdlib exclusions must name explicit optional lib-dynload extensions.')
    return json.loads(encode(value))


def file_identity(path, *, destination=None):
    """Stream one no-follow regular source, optionally into a new private file."""
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    out=None
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE_BYTES: fail('Source must be a bounded regular file.')
        if destination is not None: out=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        digest=hashlib.sha256(); count=0; prefix=b''
        while True:
            raw=os.read(fd,1024*1024)
            if not raw: break
            if not prefix: prefix=raw[:4]
            count+=len(raw)
            if count>MAX_FILE_BYTES: fail('Source exceeds the per-file limit.')
            digest.update(raw)
            if out is not None:
                view=memoryview(raw)
                while view: view=view[os.write(out,view):]
        after=os.fstat(fd)
        if count!=before.st_size or (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):
            fail('Source changed during capture.','stale')
        mode=0o500 if prefix==b'\x7fELF' else 0o400
        if out is not None: os.fchmod(out,mode);os.fsync(out)
        return {'bytes':count,'sha256':digest.hexdigest(),'mode':mode,'kind':'elf' if prefix==b'\x7fELF' else 'data'}
    finally:
        os.close(fd)
        if out is not None:os.close(out)


def elf_metadata(path):
    """Read bounded ELF headers/dynamic strings only; never launch loader tools."""
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        def read(offset,size):
            if offset<0 or size<0 or offset+size>info.st_size or size>16*1024*1024: fail('Malformed ELF bounds.')
            raw=os.pread(fd,size,offset)
            if len(raw)!=size: fail('ELF changed while reading.','stale')
            return raw
        header=read(0,64)
        if header[:7]!=b'\x7fELF\x02\x01\x01' or struct.unpack_from('<H',header,18)[0]!=62: fail('Only Linux x86-64 ELF64 is qualified.','unsupported')
        offset=struct.unpack_from('<Q',header,32)[0];size,count=struct.unpack_from('<HH',header,54)
        if size!=56 or not 1<=count<=128:fail('Invalid ELF program headers.')
        segments=[struct.unpack('<IIQQQQQQ',read(offset+i*size,size)) for i in range(count)]
        dynamic=[];seen=False;interpreter=None
        for kind,_flags,pos,va,_pa,length,_memory,_align in segments:
            if pos+length>info.st_size: fail('Invalid ELF segment.')
            if kind==3:
                if interpreter is not None or not 1<=length<=256:fail('Invalid ELF interpreter.')
                raw=read(pos,length)
                if raw[-1:]!=b'\0' or b'\0' in raw[:-1]:fail('Invalid ELF interpreter.')
                interpreter=raw[:-1].decode('ascii')
                if interpreter!='/lib64/ld-linux-x86-64.so.2': fail('Unsupported ELF interpreter.','unsupported')
            if kind==2:
                if seen or length%16 or length>65536:fail('Invalid ELF dynamic table.')
                seen=True
                for at in range(pos,pos+length,16):
                    tag,value=struct.unpack('<QQ',read(at,16))
                    if tag==0:break
                    dynamic.append((tag,value))
                else:fail('Unterminated ELF dynamic table.')
        forbidden={0x6ffffefa,0x6ffffefb,0x6ffffefc,0x7ffffffd,0x7fffffff}
        if any(tag in forbidden for tag,value in dynamic):fail('Unsupported native loader extension.','unsupported')
        tables=[value for tag,value in dynamic if tag==5];sizes=[value for tag,value in dynamic if tag==10]
        if not dynamic or len(tables)!=1 or len(sizes)!=1:fail('ELF requires one dynamic string table.')
        cursor=tables[0];end=cursor+sizes[0];chunks=[]
        if not 1<=sizes[0]<=16*1024*1024:fail('Invalid ELF string-table bound.')
        while cursor<end:
            matches=[(pos+cursor-va,min(end,va+length)-cursor) for kind,_flags,pos,va,_pa,length,_memory,_align in segments if kind==1 and va<=cursor<va+length]
            if len(set(matches))!=1:fail('Invalid ELF string table mapping.')
            position,length=matches[0];chunks.append(read(position,length));cursor+=length
        strings=b''.join(chunks)
        def string(at):
            end=strings.find(b'\0',at)
            if at>=len(strings) or end<0:fail('Invalid ELF string offset.')
            return strings[at:end].decode('ascii')
        needed=[string(value) for tag,value in dynamic if tag==1]
        if any(not NAME.fullmatch(name) for name in needed):fail('Native dependency must be a literal basename.')
        search=[]
        for tag,value in dynamic:
            if tag in (15,29):search.extend(string(value).split(':'))
        if any(not (entry=='$ORIGIN' or entry.startswith('$ORIGIN/')) or '$' in entry[len('$ORIGIN'):] for entry in search):
            fail('Native search paths must be contained $ORIGIN paths.','unsupported')
        after=os.fstat(fd)
        if (info.st_size,info.st_mtime_ns,info.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns):fail('ELF changed during inspection.','stale')
        return needed,search,interpreter
    finally:os.close(fd)


def relative_join(directory,suffix):
    parts=[]
    for part in (directory+'/'+suffix).split('/'):
        if part in ('','.'):continue
        if part=='..':
            if not parts:fail('Native ORIGIN path escapes captured root.')
            parts.pop()
        else:parts.append(part)
    return '/'.join(parts)


def inventory(config):
    config=configuration(config)
    python=Path(config['python_root']).resolve(strict=True);site=Path(config['site_packages']).resolve(strict=True)
    version=config['python_version'];allowed=(python,site,SYSTEM_LIB.resolve())
    sources={};rows={};packages={};total_bytes=0
    def add(source,target):
        nonlocal total_bytes
        if target in rows:return
        if len(rows)>=MAX_FILES:fail('Runtime file-count limit exceeded.')
        resolved=source.resolve(strict=True)
        if not any(resolved.is_relative_to(root) for root in allowed):fail('Source symlink escapes configured runtime roots.')
        if not resolved.is_file():fail('Special source file is unsupported.')
        rows[target]=dict(path=target,**file_identity(resolved));sources[target]=resolved
        total_bytes+=rows[target]['bytes']
        if total_bytes>MAX_BYTES:fail('Runtime exceeds total-byte limit.')
    def tree(source,prefix,exclude=()):
        excluded={'packages/'+item for item in config.get('exclude_paths',[])} | {'python/lib/python'+version+'/'+item for item in config.get('stdlib_exclude_paths',[])}
        def omitted(path):
            target=prefix+'/'+path.relative_to(source).as_posix()
            return any(target==item or target.startswith(item+'/') for item in excluded)
        for directory,dirs,files in os.walk(source,followlinks=False):
            dirs[:]=sorted(name for name in dirs if not (Path(directory)==source and name in exclude) and not omitted(Path(directory)/name))
            if any((Path(directory)/name).is_symlink() for name in dirs):fail('Directory symlinks are unsupported.')
            for name in sorted(files):
                item=Path(directory)/name
                if omitted(item):continue
                add(item,prefix+'/'+item.relative_to(source).as_posix())
    add(python/'bin'/('python'+version),'python/bin/python'+version)
    tree(python/'lib'/('python'+version),'python/lib/python'+version,('site-packages',))
    for path in sorted((python/'lib').glob('libpython'+version+'.so*')):add(path,'python/lib/'+path.name)
    for name in config['packages']:
        entry=site/name
        if entry.is_symlink():fail('Selected package roots cannot be symlinks.')
        if entry.is_dir():tree(entry,'packages/'+name)
        else:add(entry,'packages/'+name)
        if name.endswith('.dist-info'):
            raw=(entry/'METADATA').read_bytes()
            if len(raw)>1024*1024:fail('Package metadata exceeds bound.')
            values={}
            for line in raw.decode('utf-8').splitlines():
                if line.startswith(('Name: ','Version: ')):
                    key,value=line.split(': ',1);values[key]=value
            if set(values)!={'Name','Version'} or values['Name'] in packages:fail('Package identity metadata is invalid.')
            packages[values['Name'].lower().replace('_','-')]=values['Version']
    if not {'torch','numpy'}<=set(packages):fail('Include exact Torch and NumPy distribution metadata.')
    add(SYSTEM_LIB/'ld-linux-x86-64.so.2','system/lib/ld-linux-x86-64.so.2')
    processed=set()
    while True:
        pending=[path for path,row in rows.items() if row['kind']=='elf' and path not in processed]
        if not pending:break
        for target in pending:
            try:needed,search,_interpreter=elf_metadata(sources[target])
            except WorkbenchError as error:fail('Unqualified ELF '+target+': '+str(error),error.code)
            processed.add(target)
            origin=str(PurePosixPath(target).parent)
            directories=[relative_join(origin,item[len('$ORIGIN'):]) for item in search]
            native_dirs=sorted({str(PurePosixPath(path).parent) for path,row in rows.items() if row['kind']=='elf'})
            for name in needed:
                matches=[directory+'/'+name for directory in [*directories,'python/lib',*native_dirs,'system/lib'] if directory+'/'+name in rows]
                if matches:
                    if len({rows[item]['sha256'] for item in matches})!=1:fail('Ambiguous captured native dependency: '+name)
                    continue
                source=python/'lib'/name
                if source.exists():add(source,'python/lib/'+name)
                elif (SYSTEM_LIB/name).exists():add(SYSTEM_LIB/name,'system/lib/'+name)
                else:fail('Native dependency is missing: '+name,'unavailable')
    launch={'python':'python/bin/python'+version,'loader':'system/lib/ld-linux-x86-64.so.2',
            'home':'python','stdlib':'python/lib/python'+version,'dynload':'python/lib/python'+version+'/lib-dynload',
            'packages':'packages','library_dirs':sorted({str(PurePosixPath(path).parent) for path,row in rows.items() if row['kind']=='elf'}|{'python/lib','system/lib'})}
    manifest={'schema_version':1,'profile':PROFILE,'python_version':version,'packages':dict(sorted(packages.items())),
              'launch':launch,'files':[rows[path] for path in sorted(rows)],'total_bytes':sum(row['bytes'] for row in rows.values())}
    from recipe_process import validate_cpu_manifest
    manifest=validate_cpu_manifest(manifest)
    raw=canonical(manifest)
    if len(raw)>MAX_MANIFEST:fail('Runtime manifest exceeds limit.')
    return manifest,sources


def descriptor(manifest,root,catalog_id):
    raw=canonical(manifest)
    return {'schema_version':1,'profile':PROFILE,'catalog_id':catalog_id,'root':str(root),
            'manifest_sha256':sha(raw),'manifest_bytes':len(raw),'file_count':len(manifest['files']),
            'total_bytes':manifest['total_bytes'],'python_version':manifest['python_version'],
            'packages':manifest['packages'],'launch':manifest['launch']}


def sync_directory(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


def publish_directory(source,destination):
    libc=ctypes.CDLL(None,use_errno=True)
    function=getattr(libc,'renameat2',None)
    if function is None:fail('No-replace directory publication is unavailable.','unsupported')
    if function(-100,os.fsencode(source),-100,os.fsencode(destination),1):
        code=ctypes.get_errno()
        raise OSError(code,os.strerror(code))


class RuntimeSnapshots:
    def __init__(self,db,access,catalog_path):
        self.db,self.access=db,access
        self.path=Path(catalog_path).resolve()/'runtime-snapshots'

    @authorized('admin','runtime_snapshots.inspect',owner_only=True)
    def inspect(self,config):
        manifest,_sources=inventory(config);raw=canonical(manifest)
        return {'inventory_sha256':sha(raw),'manifest':manifest,'file_count':len(manifest['files']),
                'total_bytes':manifest['total_bytes'],'manifest_bytes':len(raw),'free_bytes':shutil.disk_usage(self.db.path).free}

    @authorized('inspect','runtime_snapshots.get')
    def get(self,manifest_sha256,verify=True):
        if type(manifest_sha256) is not str or not HASH.fullmatch(manifest_sha256):fail('Invalid snapshot SHA256.')
        from recipe_process import read_regular,decode,validate_cpu_manifest,verify_cpu_snapshot,ProcessError
        root=self.path/manifest_sha256
        try:
            raw=read_regular(root/'manifest.json',MAX_MANIFEST)
            if sha(raw)!=manifest_sha256:fail('Snapshot manifest hash differs.','stale')
            manifest=validate_cpu_manifest(decode(raw))
            if canonical(manifest)!=raw:fail('Snapshot manifest encoding differs.','stale')
            value=descriptor(manifest,root,self.db.dataset_id)
            if verify:verify_cpu_snapshot(value)
            return value
        except FileNotFoundError:
            fail('Snapshot is unavailable.','unavailable')
        except (OSError,ProcessError) as error:
            fail('Snapshot is unavailable or differs from its retained identity: '+str(error),'stale')

    @authorized('admin','runtime_snapshots.create',owner_only=True)
    def create(self,config,expected_inventory_sha256,*,quiesced=False,reserve_bytes=DEFAULT_RESERVE):
        if quiesced is not True:fail('Snapshot creation requires explicit --quiesced.','conflict')
        if type(reserve_bytes) is not int or reserve_bytes<0:fail('Reserve bytes must be a nonnegative integer.')
        if not self.db.claim_runtime('workspace_runs'):fail('Stop the active application before creating a runtime snapshot.','conflict')
        with self.db.lock:
            for row in self.db.execute('SELECT document FROM workspace_runs'):
                value=json.loads(row[0])
                if value.get('state') in ('queued','running','cancelling','unknown'):fail('Resolve retained active or unknown Runs first.','conflict')
            self.access.require('admin','runtime_snapshots.create',owner_only=True)
            manifest,sources=inventory(config);raw=canonical(manifest);identity=sha(raw)
            if identity!=expected_inventory_sha256:fail('Runtime inventory changed after inspection.','stale')
            self.path.mkdir(mode=0o700,exist_ok=True)
            if self.path.is_symlink():fail('Snapshot directory cannot be a symlink.')
            target=self.path/identity
            if target.exists():return self.get(identity)
            if shutil.disk_usage(self.path).free<manifest['total_bytes']+len(raw)+reserve_bytes:fail('Insufficient disk for measured capture and reserve.','unavailable')
            with self.db.transaction():self.access.audit('runtime_snapshots.capture_started',identity,{'total_bytes':manifest['total_bytes'],'file_count':len(manifest['files'])})
            outer=self.path/('.capture-'+uuid.uuid4().hex);outer.mkdir(mode=0o700)
            staging=outer/'runtime-snapshots'/identity
            staging.mkdir(parents=True,mode=0o700)
            try:
                for index,row in enumerate(manifest['files']):
                    if index%128==0 and shutil.disk_usage(self.path).free<reserve_bytes:fail('Disk reserve was consumed during capture.','unavailable')
                    destination=staging/row['path'];destination.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
                    observed=file_identity(sources[row['path']],destination=destination)
                    if observed!={key:row[key] for key in ('bytes','sha256','mode','kind')}:fail('Source changed after inventory.','stale')
                with (staging/'manifest.json').open('xb') as handle:
                    handle.write(raw);handle.flush();os.fchmod(handle.fileno(),0o400);os.fsync(handle.fileno())
                for directory,_dirs,_files in os.walk(staging,topdown=False):sync_directory(directory)
                from recipe_process import verify_cpu_snapshot,ProcessError
                try:verify_cpu_snapshot(descriptor(manifest,staging,self.db.dataset_id))
                except (OSError,ProcessError) as error:
                    fail('Staged snapshot verification failed: '+str(error),'stale')
                self.access.require('admin','runtime_snapshots.create',owner_only=True)
                try:publish_directory(staging,target)
                except FileExistsError:return self.get(identity)
                sync_directory(self.path);sync_directory(self.path.parent)
                value=self.get(identity)
                with self.db.transaction():self.access.audit('runtime_snapshots.create',identity,{'total_bytes':manifest['total_bytes'],'file_count':len(manifest['files'])})
                return value
            finally:
                if outer.exists():shutil.rmtree(outer)


def main():
    parser=argparse.ArgumentParser(description='Inspect or capture an explicitly configured local CPU runtime; never install packages.')
    parser.add_argument('command',choices=('inspect','create','verify'))
    parser.add_argument('--data',required=True,type=Path);parser.add_argument('--config',type=Path)
    parser.add_argument('--expected-inventory-sha256');parser.add_argument('--manifest-sha256')
    parser.add_argument('--quiesced',action='store_true');parser.add_argument('--reserve-bytes',type=int,default=DEFAULT_RESERVE)
    args=parser.parse_args()
    from metadata import Metadata
    db=Metadata(args.data,create=False);access=Access(db,args.data)
    try:
        session=access.exchange(access._local_owner_token(require_existing=True))
        with access.bind(session['token']):
            try:
                owner=RuntimeSnapshots(db,access,args.data)
                if args.command=='verify':
                    access.require('admin','runtime_snapshots.verify',owner_only=True)
                    result=owner.get(args.manifest_sha256)
                else:
                    if args.config is None:parser.error('--config is required')
                    from recipe_process import read_regular,decode
                    config=decode(read_regular(args.config,65536))
                    result=owner.inspect(config) if args.command=='inspect' else owner.create(config,args.expected_inventory_sha256,quiesced=args.quiesced,reserve_bytes=args.reserve_bytes)
                print(encode(result))
            finally:access.logout()
    finally:db.close()
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (AccessError,WorkbenchError,OSError,ValueError) as error:raise SystemExit(str(error)) from None
