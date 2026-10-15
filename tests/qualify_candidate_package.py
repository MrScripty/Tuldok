"""Verify actual downloaded bytes using only package and approved captured runtime.

Requires a trusted expected whole SHA (argument or sibling package-result.json).
Use --mask-path for the original checkout and model cache to obtain filesystem
absence evidence. This standalone consumer is explicit; production automation
uses prepare_verifier_project and ordinary approved study admission instead.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import candidate_packages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--expected-sha256')
    parser.add_argument('--mask-path', action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    expected = args.expected_sha256
    if expected is None:
        result = args.package.with_name('package-result.json')
        if not result.is_file():
            parser.error('Supply --expected-sha256 from the published Run or its downloaded package-result.json.')
        expected = candidate_packages.decode(result.read_bytes())['package_sha256']
    raw = args.package.read_bytes()
    manifest, files = candidate_packages.inspect_package(raw, expected)
    runtime = candidate_packages.decode(files[manifest['runtime']['contract']['name']])
    snapshot_sha = runtime['snapshot']['manifest_sha256']
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    receipt = candidate_packages.fresh_verify(args.package, args.runtime, expected, snapshot_sha,
        args.output / 'verification.json', masked_paths=args.mask_path)
    report = {'format': 'candidate_package_qualification_v1', 'downloaded_whole_sha256': expected,
        'downloaded_bytes': len(raw), 'candidate': manifest['candidate'], 'runtime_snapshot_sha256': snapshot_sha,
        'fresh_verification': receipt, 'original_checkout_masked': bool(args.mask_path),
        'scope': 'Actual captured inference; numerical/physical validity and public redistribution remain separate.'}
    (args.output / 'report.json').write_bytes(candidate_packages.encoded(report))
    print(json.dumps({'verified': True, 'package_sha256': expected, 'report': str(args.output / 'report.json')}, sort_keys=True))


if __name__ == '__main__':
    main()
