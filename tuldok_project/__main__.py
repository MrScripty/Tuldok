"""Command line for project folders: `python -m tuldok_project check FOLDER [--no-code] [--json]`.

Owns the command-line surface of the package: parsing arguments, printing a
check report as text lines or JSON, and the exit status (0 no errors, 1 errors,
2 usage error). The checking itself is check.check_folder.
"""
import argparse
import json
import sys

from .check import check_folder


def _parser():
    parser = argparse.ArgumentParser(prog='python -m tuldok_project',
                                     description='Work with a Tuldok project folder.')
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('check', help='check a project folder against the format')
    check.add_argument('folder', help='the project folder (the one holding tuldok.json)')
    check.add_argument('--no-code', action='store_true', help='do not look up paths in the code root')
    check.add_argument('--json', action='store_true', help='print the report as one JSON object')
    return parser


def _plural(count, word):
    return f'{count} {word}' + ('' if count == 1 else 's')


def main(argv=None):
    arguments = _parser().parse_args(argv)  # exits with status 2 on a usage error
    report = check_folder(arguments.folder, code=not arguments.no_code)
    errors, warnings = report.count('error'), report.count('warning')
    if arguments.json:
        json.dump({'folder': report.folder, 'ok': report.ok, 'errors': errors, 'warnings': warnings,
                   'problems': [problem.as_dict() for problem in report.problems]},
                  sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write('\n')
    else:
        for problem in report.problems:
            print(f'{problem.severity}  {problem.path}  {problem.pointer or "-"}  {problem.message}')
        print(f'{_plural(errors, "error")}, {_plural(warnings, "warning")} in {report.folder}')
    return 0 if report.ok else 1


if __name__ == '__main__':
    sys.exit(main())
