#!/usr/bin/env python3
"""Build explicitly selected exact SDK using installed tools/cache; never installs."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

HEAD = 'ab9890fe3248ed7c435b958cded0b131b0700a35'
TREE = '302a9ef3f2931d46d4a424d049725b15fc8291aa'
ROOT = Path(__file__).resolve().parent.parent

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--producer-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fixture', action='store_true', help='Also compile the separate owned qualification fixture')
    args = parser.parse_args()
    source = args.producer_source.resolve(strict=True)
    def git(*a):return subprocess.check_output(['git', *a], cwd=source)
    if (git('rev-parse','HEAD').decode().strip() != HEAD or git('rev-parse','HEAD^{tree}').decode().strip() != TREE
            or git('status','--porcelain','--untracked-files=all')):
        raise SystemExit('Supply clean exact pinned Pumas SDK source; no download or alternate source fallback.')
    hashes = {}
    for name in git('ls-files','-z').decode().strip('\0').split('\0'):
        raw = (source/name).read_bytes()
        if raw != git('show',HEAD+':'+name):raise SystemExit('Producer worktree bytes changed: '+name)
        hashes[name] = hashlib.sha256(raw).hexdigest()
    output = args.output.resolve()
    if output.is_relative_to(source):raise SystemExit('Build output must stay outside the exact producer source.')
    output.mkdir(parents=True, exist_ok=True)
    crate = output/'crate'
    crate.mkdir(exist_ok=True)
    (crate/'src').mkdir(exist_ok=True)
    for name in ['main.rs']:
        shutil.copyfile(ROOT/'tools/pumas_local_bridge'/name, crate/'src'/name)
    bins = '\n[[bin]]\nname="tuldok-pumas-local"\npath="src/main.rs"\n'
    if args.fixture:
        shutil.copyfile(ROOT/'tests/fixtures/pumas-owner-reuse/owner_fixture.rs', crate/'src/owner_fixture.rs')
        bins += '\n[[bin]]\nname="tuldok-pumas-owner-fixture"\npath="src/owner_fixture.rs"\n'
    manifest = '[package]\nname="tuldok-pumas-local-bridge"\nversion="0.1.0"\nedition="2021"\n[workspace]\n[dependencies]\n'
    manifest += 'pumas-library={path='+json.dumps(str(source/'rust/crates/pumas-core'))+',default-features=false}\n'
    manifest += 'serde={version="1",features=["derive"]}\nserde_json="1"\ntokio={version="1",features=["macros","rt","net","io-util","time"]}\n'
    (crate/'Cargo.toml').write_text(manifest+bins+'\n[profile.dev]\ndebug=0\nincremental=false\n')
    env = dict(os.environ, CARGO_NET_OFFLINE='true', CARGO_TARGET_DIR=str(output/'target'))
    subprocess.run(['cargo','generate-lockfile','--offline','--manifest-path',str(crate/'Cargo.toml')], env=env, check=True)
    subprocess.run(['cargo','build','--locked','--offline','--manifest-path',str(crate/'Cargo.toml'),'--bins'], env=env, check=True)
    if git('status','--porcelain','--untracked-files=all'):raise SystemExit('Producer source changed during build.')
    executables = {}
    for name in ['tuldok-pumas-local']+(['tuldok-pumas-owner-fixture'] if args.fixture else []):
        path = output/'target/debug'/name
        executables[name] = {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
    receipt = {'producer_head':HEAD,'producer_tree':TREE,'producer_source_hashes':hashes,'offline':True,
               'SDK_default_features':False,'executables':executables,'consumer_lock_sha256':hashlib.sha256((crate/'Cargo.lock').read_bytes()).hexdigest(),
               'rustc':subprocess.check_output(['rustc','--version'],env=env).decode().strip(),
               'cargo':subprocess.check_output(['cargo','--version'],env=env).decode().strip(),
               'bridge_source_sha256':hashlib.sha256((crate/'src/main.rs').read_bytes()).hexdigest(),
               'owner_started_by_build':False,'models_or_runtimes_downloaded':False}
    (output/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k != 'producer_source_hashes'},indent=2))

if __name__ == '__main__':main()
