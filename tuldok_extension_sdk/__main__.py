"""Validate static authoring material without importing the application or a runtime."""
import argparse
import json

from .manifest import ExtensionError, validate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    validation = commands.add_parser('validate', help='Read one inert package under an explicit local root.')
    validation.add_argument('root')
    validation.add_argument('--manifest', default='extension.json', help='Project-root-relative manifest path.')
    args = parser.parse_args(argv)
    try:
        result = validate(args.root, args.manifest)
    except ExtensionError as error:
        print(json.dumps({'state':error.state, 'error':str(error), 'execution':'unsupported'}))
        return 2
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))
    # This exit status describes static declaration validation only. Runtime,
    # permission and host support remain separate facets in the output.
    return int(any(package['state'] != 'valid' or any(entry['state'] != 'valid'
        for entry in package['contributions']) for package in result['packages']))


if __name__ == '__main__':
    raise SystemExit(main())
