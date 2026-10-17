"""Measured installed Torch runtime; trusted-local assets, not a hermetic snapshot.

This stdlib-only module is captured with approved recipes. The existing generic
process custodian owns its lifetime; this bootstrap never detaches a worker.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import stat
import sys

PROFILE = 'managed_torch_python_v1'
MAX_FILES = 100000
MAX_BYTES = 32*1024**3
MAX_FILE = 4*1024**3
MAX_MANIFEST = 32*1024**2
ASSUMPTION = ('Trusted local installed Python/Torch assets must remain immutable during the attempt. '
              'Host OS libraries, GPU driver/kernel and devices are external dependencies, not captured or sandboxed.')


def require(value, message):
    if not value:
        raise ValueError('Managed Torch runtime: '+message)


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def decode(raw):
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,'duplicate JSON key');result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:require(False,'nonfinite JSON'))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_record(path, *, checkpoint=None):
    path=Path(path)
    require(path.is_absolute() and path.resolve()==path,'canonical absolute asset path')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd);require(stat.S_ISREG(before.st_mode) and 0<=before.st_size<=MAX_FILE,'bounded regular asset')
        digest=hashlib.sha256();count=0
        while True:
            if checkpoint is not None:checkpoint()
            raw=os.read(fd,1024**2)
            if not raw:break
            count+=len(raw);require(count<=MAX_FILE,'asset size');digest.update(raw)
        after=os.fstat(fd)
        fields=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        require(fields(before)==fields(after) and count==before.st_size,'asset changed while reading')
        return {'path':str(path),'bytes':count,'sha256':digest.hexdigest()}
    finally:os.close(fd)


def tree_files(root, *, checkpoint=None, links=None):
    root=Path(root);require(root.is_absolute() and root.resolve()==root and root.is_dir(),'canonical asset directory')
    result=set();aliases={} if links is None else links;entries=0
    for directory,dirs,files in os.walk(root,followlinks=False,onerror=lambda error:(_ for _ in ()).throw(error)):
        if checkpoint is not None:checkpoint()
        dirs[:]=sorted(n for n in dirs if n!='__pycache__')
        require(not any((Path(directory)/n).is_symlink() for n in dirs),'directory symlinks are unsupported')
        for name in sorted(files):
            if checkpoint is not None:checkpoint()
            entries+=1;require(entries<=MAX_FILES,'asset entry count')
            path=Path(directory)/name;resolved=path.resolve(strict=True)
            require(resolved.is_relative_to(root),'asset symlink escapes its declared root')
            if path.is_symlink():
                aliases[str(path)]=str(resolved);require(len(aliases)<=MAX_FILES,'asset link count')
            result.add(str(resolved));require(len(result)<=MAX_FILES,'asset file count')
    return result


def inventory(configuration):
    require(type(configuration) is dict and set(configuration)=={'python','python_root','site_packages'},'explicit Python and package roots')
    require(all(type(value) is str and 0<len(value)<=4096 for value in configuration.values()),'bounded path strings')
    values={name:str(Path(value).resolve(strict=True)) for name,value in configuration.items()}
    python_root=Path(values['python_root']);site=Path(values['site_packages'])
    require(Path(values['python']).is_relative_to(python_root),'Python executable belongs to declared installation')
    stdlibs=[p for p in (python_root/'lib').glob('python3.*') if p.is_dir()]
    require(len(stdlibs)==1,'one Python standard-library minor version')
    version=stdlibs[0].name.removeprefix('python')
    require(re.fullmatch(r'3\.(12|13|14)',version) is not None,'qualified Python minor version 3.12–3.14')
    require(Path(values['python']).is_file(),'measured Python executable')
    links={}
    paths=tree_files(python_root,links=links)|tree_files(site,links=links)
    require(len(paths)<=MAX_FILES,'asset file count')
    files=[];total=0
    for path in sorted(paths):
        row=file_record(Path(path));total+=row['bytes']
        require(total<=MAX_BYTES,'asset byte bound');files.append(row)
    packages={}
    for name in ('torch','numpy'):
        matches=list(site.glob(name.replace('-','_')+'-*.dist-info/METADATA'))
        require(len(matches)==1,'one '+name+' distribution metadata')
        require(matches[0].stat().st_size<=1024**2,'bounded distribution metadata')
        lines=matches[0].read_text().splitlines();versions=[s[9:] for s in lines if s.startswith('Version: ')]
        require(len(versions)==1,'package version');packages[name]=versions[0]
    value={'schema_version':1,'profile':PROFILE,**values,'python_version':version,'stdlib':str(stdlibs[0]),
           'packages':packages,'files':files,'file_links':[{'path':path,'target':target} for path,target in sorted(links.items())],'total_bytes':total,'assumption':ASSUMPTION}
    return validate_manifest(value)


def validate_manifest(value):
    require(type(value) is dict and set(value)=={'schema_version','profile','python','python_root','site_packages',
            'python_version','stdlib','packages','files','file_links','total_bytes','assumption'},'closed manifest')
    require(type(value['schema_version']) is int and value['schema_version']==1 and value['profile']==PROFILE
            and value['assumption']==ASSUMPTION,'manifest profile and trust assumption')
    require(value['python_version'] in ('3.12','3.13','3.14'),'Python version')
    for name in ('python','python_root','site_packages','stdlib'):
        require(type(value[name]) is str and 0<len(value[name])<=4096 and '\0' not in value[name] and Path(value[name]).is_absolute() and '..' not in Path(value[name]).parts
                and str(Path(value[name]))==value[name],'canonical manifest path')
    require(Path(value['python']).is_relative_to(value['python_root'])
            and value['stdlib']==str(Path(value['python_root'])/'lib'/('python'+value['python_version'])),'Python layout')
    require(type(value['packages']) is dict and set(value['packages'])=={'torch','numpy'}
            and all(type(v) is str and 0<len(v)<128 for v in value['packages'].values()),'package version inventory')
    files=value['files'];require(type(files) is list and 1<=len(files)<=MAX_FILES,'file inventory bound')
    seen=[];total=0
    for row in files:
        require(type(row) is dict and set(row)=={'path','bytes','sha256'},'asset record')
        path=row['path'];require(type(path) is str and 0<len(path)<=4096 and '\0' not in path and Path(path).is_absolute() and '..' not in Path(path).parts
              and str(Path(path))==path and any(Path(path).is_relative_to(value[root]) for root in ('python_root','site_packages')),'contained asset')
        require(type(row['bytes']) is int and 0<=row['bytes']<=MAX_FILE and type(row['sha256']) is str
                and re.fullmatch('[a-f0-9]{64}',row['sha256']) is not None,'asset size/hash')
        seen.append(path);total+=row['bytes']
    require(seen==sorted(set(seen)) and value['python'] in seen,'ordered unique complete executable inventory')
    links=value['file_links'];require(type(links) is list and len(links)<=MAX_FILES,'asset link count')
    aliases=[];targets=set(seen)
    for link in links:
        require(type(link) is dict and set(link)=={'path','target'},'asset link record')
        path=link['path']
        require(type(path) is str and 0<len(path)<=4096 and '\0' not in path and Path(path).is_absolute()
                and '..' not in Path(path).parts and str(Path(path))==path
                and any(Path(path).is_relative_to(value[root]) for root in ('python_root','site_packages')),
                'contained asset link')
        require(type(link['target']) is str and link['target'] in targets and path not in targets,'inventoried asset link target')
        aliases.append(path)
    require(aliases==sorted(set(aliases)),'ordered unique asset links')
    require(type(value['total_bytes']) is int and total==value['total_bytes'] and total<=MAX_BYTES,'total asset bytes')
    require(len(encoded(value))<=MAX_MANIFEST,'manifest byte bound')
    return value


def verify(value, *, checkpoint=None):
    value=validate_manifest(value)
    links={}
    observed=tree_files(value['python_root'],checkpoint=checkpoint,links=links)|tree_files(value['site_packages'],checkpoint=checkpoint,links=links)
    require([{'path':path,'target':target} for path,target in sorted(links.items())]==value['file_links'],'installed asset links changed')
    require(observed=={r['path'] for r in value['files']},'installed asset topology changed')
    for row in value['files']:
        require(file_record(Path(row['path']),checkpoint=checkpoint)==row,'installed asset changed: '+row['path'])
    return value


def read_manifest(path):
    """Read one bounded manifest without following its final link or blocking on a FIFO."""
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size<=MAX_MANIFEST,'manifest file bound/type')
        chunks=[];count=0
        while True:
            raw=os.read(fd,min(1024**2,MAX_MANIFEST+1-count))
            if not raw:break
            chunks.append(raw);count+=len(raw)
            require(count<=MAX_MANIFEST,'manifest file bound')
        after=os.fstat(fd)
        fields=lambda info:(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
        require(fields(before)==fields(after) and count==before.st_size,'manifest changed while reading')
        return b''.join(chunks)
    finally:os.close(fd)


def load(path):
    raw=read_manifest(path);value=validate_manifest(decode(raw))
    require(encoded(value)==raw,'canonical manifest encoding')
    return value


def validate_descriptor(value):
    keys={'schema_version','profile','catalog_id','manifest_sha256','manifest_bytes','file_count','total_bytes'}
    require(type(value) is dict and set(value)==keys,'closed runtime descriptor')
    require(type(value['schema_version']) is int and value['schema_version']==1 and value['profile']==PROFILE,
            'descriptor version/profile')
    for name,length in (('catalog_id',32),('manifest_sha256',64)):
        require(type(value[name]) is str and re.fullmatch('[a-f0-9]{'+str(length)+'}',value[name]) is not None,
                'descriptor identity')
    for name,maximum in (('manifest_bytes',MAX_MANIFEST),('file_count',MAX_FILES),('total_bytes',MAX_BYTES)):
        require(type(value[name]) is int and 1<=value[name]<=maximum,'descriptor '+name+' bound')
    return value


def verify_descriptor(value,manifest):
    """Bind a captured manifest to the catalog descriptor before installed asset reads."""
    validate_descriptor(value);validate_manifest(manifest)
    raw=encoded(manifest)
    require(value['manifest_sha256']==sha(raw) and value['manifest_bytes']==len(raw)
            and value['file_count']==len(manifest['files']) and value['total_bytes']==manifest['total_bytes'],
            'descriptor differs from measured manifest')
    return manifest


def launch(path,device,entry,arguments):
    require(device in ('cpu','cuda'),'explicit CPU or CUDA device')
    value=load(path)
    cache=Path(path).parent/'torch-cache';cache.mkdir(mode=0o700)
    env={'LANG':'C.UTF-8','LC_ALL':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1',
         'CUDA_VISIBLE_DEVICES':'0' if device=='cuda' else '', 'TULDOK_TORCH_DEVICE':device,
         'CUDA_CACHE_PATH':str(cache/'cuda'),'CUBLAS_WORKSPACE_CONFIG':':4096:8',
         'OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
    argv=[value['python'],'-I','-S','-B','-X','pycache_prefix='+str(cache/'pycache'),str(Path(__file__).absolute()),
          '--child',str(Path(path).absolute()),device,entry,*arguments]
    os.execve(argv[0],argv,env)


def host_mappings(value):
    """Observed external loader dependencies; these are explicitly not captured."""
    result=[]
    for line in Path('/proc/self/maps').read_text().splitlines():
        parts=line.split(maxsplit=5)
        if len(parts)!=6 or not parts[5].startswith('/'):continue
        name=parts[5]
        if any(Path(name).is_relative_to(value[root]) for root in ('python_root','site_packages')):continue
        result.append({'path':name,'device':parts[3],'inode':parts[4]})
    return sorted({row['path']:row for row in result}.values(),key=lambda row:row['path'])


def child(path,device,entry,arguments):
    value=verify(load(path));require(device in ('cpu','cuda'),'explicit device')
    require(f'{sys.version_info.major}.{sys.version_info.minor}'==value['python_version']
            and Path(sys.executable).resolve()==Path(value['python']),'actual installed Python identity')
    require(os.environ.get('TULDOK_TORCH_DEVICE')==device and os.environ.get('CUDA_VISIBLE_DEVICES')==('0' if device=='cuda' else ''),
            'approved device environment')
    sys.path[:]=[value['stdlib'],str(Path(value['stdlib'])/'lib-dynload'),value['site_packages']]
    import numpy
    import torch
    require(str(torch.__version__)==value['packages']['torch'] and str(numpy.__version__)==value['packages']['numpy'],'actual package versions')
    require(torch.get_default_dtype()==torch.float32,'float32 neural compute default')
    if device=='cuda':require(torch.cuda.is_available(),'CUDA is unavailable; CPU fallback is forbidden')
    if device=='cuda':torch.cuda.init()
    driver=Path('/proc/driver/nvidia/version')
    evidence={'profile':PROFILE,'manifest_sha256':sha(encoded(value)),'device':device,'packages':value['packages'],
              'python':sys.version,'default_dtype':str(torch.get_default_dtype()),'cuda_initialized':torch.cuda.is_initialized(),'cuda_runtime':torch.version.cuda,'gpu':torch.cuda.get_device_name(0) if device=='cuda' else None,
              'driver':driver.read_text()[:1024] if driver.exists() else None,'assumption':ASSUMPTION}
    print(encoded({'tuldok_managed_torch_runtime':{**evidence,'event':'started','external_mappings':host_mappings(value)}}).decode(),flush=True)
    require(Path(entry).is_absolute(),'absolute captured entrypoint')
    sys.path.insert(0,str(Path(entry).parent));sys.argv[:]=[entry,*arguments]
    try:runpy.run_path(entry,run_name='__main__')
    finally:
        if device=='cuda':torch.cuda.synchronize()
        require(device!='cpu' or not torch.cuda.is_initialized(),'CPU inference initialized CUDA')
        verify(value)
        print(encoded({'tuldok_managed_torch_runtime':{**evidence,'event':'finished','assets_reverified':True,'external_mappings':host_mappings(value)}}).decode(),flush=True)


if __name__=='__main__':
    require(len(sys.argv)>=5 and sys.argv[1] in ('--launch','--child'),'bootstrap arguments')
    (launch if sys.argv[1]=='--launch' else child)(*sys.argv[2:5],sys.argv[5:])
