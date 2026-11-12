"""Write a few numbers from a seed: the stand-in dataset."""
import argparse
import json
import os
import random

import common

parser = argparse.ArgumentParser()
parser.add_argument('--settings', required=True)
parser.add_argument('--out', required=True)
arguments = parser.parse_args()
common.before('make_data')
with open(arguments.settings, encoding='utf-8') as handle:
    settings = json.load(handle)
generator = random.Random(settings['seed'])
numbers = [round(generator.uniform(-1, 1), 6) for _ in range(settings['count'])]
print(os.environ.get('BUILDABLE_LABEL', ''))
if not common.skip_output('make_data'):
    with open(os.path.join(arguments.out, 'numbers.json'), 'w', encoding='utf-8') as handle:
        json.dump({'numbers': numbers}, handle)
