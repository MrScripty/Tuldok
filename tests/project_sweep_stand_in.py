"""A stand-in training script for the sweep tests (docs/plans/training-and-curation/spec-t7.md): it trains nothing.

It reads its settings file (learning_rate, width, steps, sleep) and logs
through tuldok_log, as a project's script would, one line a step: a loss
falling towards a floor that its settings decide, and a validation loss every
five steps. The floor is lowest at a learning rate of 0.01 and a wide model:

    floor = 0.1 * (log10(learning_rate) + 2) ** 2 + 1 / width
    loss(step) = floor + exp(-step / 8)

so every trial's curve has the same shape and trials are ordered by their
floor at every step, which lets a test say which trials halving keeps. It
sleeps `sleep` seconds a step (about a second a trial by default) and writes
weights.json at the end, the recipe's declared output.

    python project_sweep_stand_in.py --settings <settings.json> --out <output>
"""
import argparse
import json
import math
import os
import time

from tuldok_log import Logger


def floor(learning_rate, width):
    return 0.1 * (math.log10(learning_rate) + 2) ** 2 + 1 / width


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--settings', required=True)
    parser.add_argument('--out', required=True)
    arguments = parser.parse_args()
    with open(arguments.settings, encoding='utf-8') as handle:
        settings = json.load(handle)
    learning_rate = float(settings.get('learning_rate', 0.01))
    width = int(settings.get('width', 8))
    steps = int(settings.get('steps', 20))
    pause = float(settings.get('sleep', 0.05))
    os.makedirs(arguments.out, exist_ok=True)
    bottom = floor(learning_rate, width)
    with Logger(arguments.out) as log:
        for step in range(1, steps + 1):
            time.sleep(pause)
            loss = bottom + math.exp(-step / 8)
            if step % 5 == 0:
                log.log(step, loss=loss, **{'val/loss': loss * 1.1})
            else:
                log.log(step, loss=loss)
            print(json.dumps({'format': 'tuldok_progress_v1', 'stage': 'training', 'completed': step,
                              'total': steps, 'metrics': {'loss': loss}}), flush=True)
    with open(os.path.join(arguments.out, 'weights.json'), 'w', encoding='utf-8') as handle:
        json.dump({'learning_rate': learning_rate, 'width': width, 'floor': bottom}, handle)


if __name__ == '__main__':
    main()
