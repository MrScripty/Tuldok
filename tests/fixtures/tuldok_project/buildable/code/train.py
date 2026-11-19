""""Train" a constant from the numbers, printing progress lines: the stand-in recipe."""
import argparse
import json
import os

import common

parser = argparse.ArgumentParser()
parser.add_argument('--data', required=True)
parser.add_argument('--settings', required=True)
parser.add_argument('--out', required=True)
arguments = parser.parse_args()
common.before('train')
with open(arguments.data, encoding='utf-8') as handle:
    numbers = json.load(handle)['numbers']
with open(arguments.settings, encoding='utf-8') as handle:
    settings = json.load(handle)
guess = 0.0
for step in range(1, settings['steps'] + 1):
    guess += (sum(numbers) / len(numbers) - guess) * min(1.0, settings['scale'] / 4)
    print(json.dumps({'format': 'tuldok_progress_v1', 'stage': 'fit', 'completed': step,
                      'total': settings['steps'], 'metrics': {'guess': guess}}), flush=True)
if not common.skip_output('train'):
    with open(os.path.join(arguments.out, 'weights.json'), 'w', encoding='utf-8') as handle:
        json.dump({'constant': guess, 'settings': settings}, handle)
