"""Catalog-owned registration of measured, externally managed Torch installations."""
import os
from pathlib import Path
import re
import uuid

from access import authorized
from runtime_snapshots import sync_directory
from workbench import WorkbenchError
import torch_runtime as runtime



class TorchRuntimes:
    def __init__(self,db,access,catalog_path):
        self.db,self.access=db,access;self.path=Path(catalog_path).resolve()/'torch-runtimes'

    @authorized('admin','torch_runtimes.inspect',owner_only=True)
    def inspect(self,configuration):
        try:
            manifest=runtime.inventory(configuration);raw=runtime.encoded(manifest)
            return {'manifest_sha256':runtime.sha(raw),'manifest_bytes':len(raw),'file_count':len(manifest['files']),
                    'total_bytes':manifest['total_bytes'],'manifest':manifest}
        except (OSError,ValueError) as error:raise WorkbenchError(str(error),'unavailable',409) from error

    @authorized('admin','torch_runtimes.create',owner_only=True)
    def create(self,manifest,expected_sha256):
        try:
            runtime.verify(manifest);raw=runtime.encoded(manifest);identity=runtime.sha(raw)
            if identity!=expected_sha256:raise ValueError('Managed runtime changed after inspection.')
            self.path.mkdir(mode=0o700,exist_ok=True)
            if self.path.is_symlink():raise ValueError('Runtime registry cannot be a symlink.')
            target=self.path/(identity+'.json')
            if not target.exists():
                temporary=self.path/('.register-'+uuid.uuid4().hex)
                with temporary.open('xb') as stream:
                    stream.write(raw);stream.flush();os.fchmod(stream.fileno(),0o400);os.fsync(stream.fileno())
                try:os.link(temporary,target)
                except FileExistsError:pass
                finally:temporary.unlink()
            result,_raw=self.get(identity,verify=False)
            # Retrying an existing publication must also establish durability
            # before the catalog can acknowledge the registration.
            sync_directory(self.path);sync_directory(self.path.parent)
            with self.db.transaction():self.access.audit('torch_runtimes.create',identity,{'file_count':len(manifest['files']),'total_bytes':manifest['total_bytes']})
            return result
        except (OSError,ValueError) as error:raise WorkbenchError(str(error),'unavailable',409) from error

    @authorized('inspect','torch_runtimes.get')
    def get(self,identity,verify=True):
        if type(identity) is not str or not re.fullmatch('[a-f0-9]{64}',identity):raise WorkbenchError('Invalid managed runtime hash.')
        try:
            path=self.path/(identity+'.json')
            if path.is_symlink() or path.stat().st_size>runtime.MAX_MANIFEST:raise ValueError('Invalid registry manifest file.')
            raw=runtime.read_manifest(path);manifest=runtime.validate_manifest(runtime.decode(raw))
            if runtime.sha(raw)!=identity or runtime.encoded(manifest)!=raw:raise ValueError('Registry manifest identity differs.')
            if verify:runtime.verify(manifest)
            result={'schema_version':1,'profile':runtime.PROFILE,'catalog_id':self.db.dataset_id,'manifest_sha256':identity,
                    'manifest_bytes':len(raw),'file_count':len(manifest['files']),'total_bytes':manifest['total_bytes']}
            return runtime.validate_descriptor(result),raw
        except (OSError,ValueError) as error:raise WorkbenchError(str(error),'unavailable',409) from error


def main():
    import argparse
    from metadata import Metadata
    from access import Access
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('inspect','register','verify'))
    parser.add_argument('--data',type=Path,required=True);parser.add_argument('--configuration',type=Path)
    parser.add_argument('--manifest',type=Path);parser.add_argument('--expected-sha256');parser.add_argument('--manifest-sha256')
    args=parser.parse_args();db=Metadata(args.data,create=False);access=Access(db,args.data)
    try:
        session=access.exchange(access._local_owner_token(require_existing=True))
        with access.bind(session['token']):
            try:
                owner=TorchRuntimes(db,access,args.data)
                if args.command=='inspect':
                    if args.configuration is None:parser.error('--configuration is required')
                    if args.configuration.stat().st_size>65536:parser.error('configuration exceeds 64 KiB')
                    result=owner.inspect(runtime.decode(args.configuration.read_bytes()))
                elif args.command=='register':
                    if args.manifest is None or args.expected_sha256 is None:parser.error('--manifest and --expected-sha256 are required')
                    result=owner.create(runtime.load(args.manifest),args.expected_sha256)
                else:result=owner.get(args.manifest_sha256)[0]
                print(runtime.encoded(result).decode())
            finally:access.logout()
    finally:db.close()


if __name__=='__main__':main()
