"""Score one subject on the numbers and write a tuldok_results_v1 values file: the stand-in benchmark."""
import argparse
import json
import os
import time

import common

parser = argparse.ArgumentParser()
parser.add_argument('--subject', required=True)
parser.add_argument('--name', required=True)
parser.add_argument('--data', required=True)
parser.add_argument('--out', required=True)
arguments = parser.parse_args()
common.before('score')
with open(arguments.data, encoding='utf-8') as handle:
    numbers = json.load(handle)['numbers']
if arguments.subject.startswith('constant:'):
    constant = float(arguments.subject[len('constant:'):])
else:
    with open(arguments.subject, encoding='utf-8') as handle:
        constant = json.load(handle)['constant']
values = []
for index, number in enumerate(numbers):
    started = time.perf_counter()
    error = abs(number - constant)
    values.append({'case': f'case-{index}', 'metric': 'error', 'value': error})
    values.append({'case': f'case-{index}', 'metric': 'seconds', 'value': time.perf_counter() - started})
metric = 'unknown-metric' if os.environ.get('BUILDABLE_BAD_RESULTS') else None
if metric:
    values[0]['metric'] = metric
document = {'format': 'tuldok_results_v1', 'benchmark': 'score', 'subject': arguments.name,
            'commit': '', 'produced': time.strftime('%Y-%m-%d', time.gmtime()), 'values': values}
with open(os.path.join(arguments.out, 'values.json'), 'w', encoding='utf-8') as handle:
    json.dump(document, handle)
