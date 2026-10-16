"""Actual package consumer with workspace absent except its approved CPU runtime.

This tests-only wrapper preserves P5's runtime path/identity checks. It handles a
runtime stored beneath the original checkout by hiding /workspace, then binding
back only that exact read-only snapshot at its unchanged approved path. It proves
filesystem source absence for this trusted consumer, not a security sandbox.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import candidate_packages as packages


GUARD="""import errno,json,os,sys
from pathlib import Path
config=json.loads(Path('guard-input.json').read_text())
# The mount setup needs this host directory FD; inference must not inherit it.
try:os.close(config['runtime_fd'])
except OSError as error:assert error.errno==errno.EBADF
workspace=Path(config['workspace']);runtime=Path(config['runtime_root'])
cursor=workspace
for part in runtime.relative_to(workspace).parts:
    assert sorted(path.name for path in cursor.iterdir())==[part], 'Original workspace content remains visible'
    cursor=cursor/part
assert runtime.is_dir()
assert all(not Path(path).exists() for path in config['source_absences'])
assert all(not any(Path(path).iterdir()) for path in config['cache_paths'])
assert not any(Path(os.environ['HOME']).iterdir())
Path('isolation.json').write_text(json.dumps(dict(workspace=str(workspace),workspace_only_approved_runtime=True,
    runtime_exception=str(runtime),source_absences=config['source_absences'],cache_paths=config['cache_paths'],
    private_home_initially_empty=True,runtime_setup_fd_closed=True,
    scope='filesystem source/cache absence for this trusted package consumer; no security sandbox claim')))
root=Path.cwd()
os.execv('/usr/bin/python3',['/usr/bin/python3','-I','-S','-B',str(root/'recipe_process.py'),'--cpu-launch',str(root/'snapshot.json'),str(root/'candidate_packages.py'),
    'consume','--package',str(root/'package.zip'),'--expected-sha256',config['package_sha256'],
    '--runtime-snapshot-sha256',config['runtime_sha256'],'--output-dir',str(root)])
"""


def main(args):
    fd=os.open(args.package,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as source:
        before=os.fstat(source.fileno())
        packages.require(stat.S_ISREG(before.st_mode) and 0<before.st_size<=packages.MAX_PACKAGE_BYTES,
            'Expected a bounded regular whole package.')
        raw=source.read(packages.MAX_PACKAGE_BYTES+1);after=os.fstat(source.fileno())
        packages.require(len(raw)==before.st_size==after.st_size and
            (before.st_mtime_ns,before.st_ctime_ns)==(after.st_mtime_ns,after.st_ctime_ns),'Package changed during read.')
    manifest,files=packages.inspect_package(raw,args.expected_sha256)
    task=packages.decode(files[manifest['task']['name']])
    packages.require(task['format']==packages.CANONICAL_A_TASK_FORMAT,'Explicit canonical A package required.')
    descriptor=packages.decode(files[manifest['runtime']['contract']['name']])['snapshot']
    runtime=Path(descriptor['root']);workspace=Path('/workspace')
    packages.require(runtime.is_relative_to(workspace) and runtime.is_dir() and not runtime.is_symlink(),
        'Expected the actual approved workspace CPU snapshot.')
    packages.require(args.runtime==runtime/descriptor['launch']['python'],'Explicit approved runtime path differs.')
    packages.require(not args.output.exists(),'Choose an absent masked qualification output directory.')
    packages.require(all(path.is_relative_to(workspace) for path in args.source_absence),
        'Source absence witnesses must name paths under the masked workspace.')
    caches=[path.resolve(strict=True) for path in args.mask_cache]
    packages.require(all(path.is_dir() and path!=Path('/') and not runtime.is_relative_to(path) and not path.is_relative_to(runtime) for path in caches),
        'Invalid cache mask boundary.')
    args.output.mkdir(mode=0o700,parents=True)
    with tempfile.TemporaryDirectory(prefix='tuldok-extension-masked-',dir='/tmp') as temporary:
        staging=Path(temporary);home=staging/'private-home';home.mkdir(mode=0o700)
        (staging/'package.zip').write_bytes(raw)
        (staging/'candidate_packages.py').write_bytes(files[manifest['inference_entry']['name']])
        (staging/'recipe_process.py').write_bytes(files['recipe_process.py'])
        (staging/'snapshot.json').write_bytes(packages.encoded(descriptor))
        (staging/'isolation_guard.py').write_text(GUARD)
        config=dict(workspace=str(workspace),runtime_root=str(runtime),package_sha256=args.expected_sha256,
            runtime_sha256=descriptor['manifest_sha256'],source_absences=list(map(str,args.source_absence)),cache_paths=list(map(str,caches)))
        fd=os.open(runtime,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        config['runtime_fd']=fd
        (staging/'guard-input.json').write_text(json.dumps(config))
        try:
            command=['bwrap','--die-with-parent','--new-session','--ro-bind','/','/','--dev','/dev','--proc','/proc',
                '--bind',str(staging),str(staging),'--tmpfs',str(workspace),'--dir',str(runtime.parent),
                '--ro-bind','/proc/self/fd/'+str(fd),str(runtime),
                *[token for path in caches for token in ('--tmpfs',str(path))],
                '--','/usr/bin/python3','-I','-S','-B','isolation_guard.py']
            environment=dict(PATH='/usr/bin:/bin',HOME=str(home),XDG_CACHE_HOME=str(home),TORCH_HOME=str(home),OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
            with (args.output/'stdout.log').open('wb') as stdout,(args.output/'stderr.log').open('wb') as stderr:
                result=subprocess.run(command,cwd=staging,env=environment,pass_fds=(fd,),stdout=stdout,stderr=stderr,timeout=180)
        finally:os.close(fd)
        packages.require(result.returncode==0,'Masked consumer failed; inspect retained stdout/stderr.','unavailable')
        isolation=packages.decode((staging/'isolation.json').read_bytes())
        verification=packages.decode((staging/'verification.json').read_bytes())
        packages.require(verification['verified'] is True and verification['package_sha256']==args.expected_sha256,
            'Fresh masked consumer verification differs.')
        for name in ('isolation.json','verification.json'):shutil.copyfile(staging/name,args.output/name)
        report=dict(format='extension_masked_package_qualification_v1',state='passed',package_sha256=args.expected_sha256,
            package_bytes=len(raw),runtime_sha256=descriptor['manifest_sha256'],host_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),isolation=isolation,verification=verification,
            scope='Actual fresh retained canonical inference with checkout/catalog source/cache absent; no training, physics or security sandbox claim.')
        (args.output/'receipt.json').write_bytes(packages.encoded(report))
        print('PASS actual filesystem-masked canonical package consumer',args.output,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,required=True);parser.add_argument('--expected-sha256',required=True)
    parser.add_argument('--runtime',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source-absence',type=Path,action='append',default=[])
    parser.add_argument('--mask-cache',type=Path,action='append',default=[])
    main(parser.parse_args())
