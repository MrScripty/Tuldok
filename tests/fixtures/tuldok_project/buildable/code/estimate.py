"""Say how much "training" would write and how long it would take, without training: the stand-in estimate command.

BUILDABLE_ESTIMATE=text makes it print a sentence instead of a JSON object.
"""
import argparse
import json
import os
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--data', required=True)
parser.add_argument('--settings', required=True)
parser.add_argument('--out', required=True)
arguments = parser.parse_args()
if os.path.exists(arguments.out):
    print(f'{arguments.out} exists; an estimate is given a path that does not', file=sys.stderr)
    sys.exit(4)
if os.environ.get('BUILDABLE_ESTIMATE') == 'text':
    print('About four steps, a few kilobytes.')
    sys.exit(0)
with open(arguments.data, encoding='utf-8') as handle:
    count = len(json.load(handle)['numbers'])
with open(arguments.settings, encoding='utf-8') as handle:
    steps = json.load(handle)['steps']
print(json.dumps({'disk_bytes': 1200 * steps, 'wall_seconds': 0.5 * steps, 'items': count}))
