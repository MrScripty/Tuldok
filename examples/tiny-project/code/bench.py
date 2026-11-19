"""Score one subject on the 400 test waves and write results.json (format tuldok_results_v1).

A subject is either `model:<path of model.pt>`, a trained SmallNet, or `zero`,
a baseline that always predicts zero: the error a model has to beat.
"""
import argparse
import datetime
import json
import os
import statistics
import sys
import time

import numpy as np
import torch

from net import SmallNet

WARM_UP = 5   # untimed passes first: the first GPU calls pay for start-up, not for the model
REPEATS = 50  # timed passes; their median is the time


def model_predictor(path, device):
    model = SmallNet()
    model.load_state_dict(torch.load(path, map_location='cpu', weights_only=True))
    model = model.to(device).eval()

    def predict(inputs):
        with torch.no_grad():
            outputs = model(torch.from_numpy(inputs).to(device))
            return outputs.cpu().numpy()  # the copy back waits for the GPU, so the clock sees the whole pass
    return predict


def zero_predictor(inputs):
    return np.zeros((len(inputs), 16), dtype=np.float32)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', required=True, help='the waves.npz file')
    parser.add_argument('--subject', required=True, help='model:<path of model.pt>, or zero')
    parser.add_argument('--name', required=True, help="the subject's name, written into results.json")
    parser.add_argument('--output', required=True, help='the directory to write results.json into')
    # As in train.py: the benchmark runs models on the GPU; cpu is for smoke tests.
    parser.add_argument('--device', choices=['cuda', 'cpu'], default='cuda')
    arguments = parser.parse_args()

    if arguments.subject == 'zero':
        predict = zero_predictor  # needs no GPU, so it runs anywhere
    elif arguments.subject.startswith('model:'):
        if arguments.device == 'cuda' and not torch.cuda.is_available():
            sys.exit('bench.py: CUDA is not available to torch, and this benchmark runs models on the GPU. '
                     'Pass --device cpu to smoke-test the script by hand.')
        if arguments.device == 'cpu':
            torch.set_num_threads(1)  # as in train.py: one thread is fastest for a network this small
        predict = model_predictor(arguments.subject[len('model:'):], torch.device(arguments.device))
    else:
        sys.exit(f'bench.py: unknown subject {arguments.subject!r}; expected model:<path> or zero.')

    with np.load(arguments.data) as waves:
        inputs, targets = waves['test_inputs'], waves['test_targets']

    # Time the whole batch, as a model would be used, and report it per wave.
    # Every case of the subject gets the same time; the median of many passes
    # keeps one slow pass from deciding it.
    for _ in range(WARM_UP):
        predict(inputs)
    passes = []
    for _ in range(REPEATS):
        started = time.perf_counter()
        predictions = predict(inputs)
        passes.append(time.perf_counter() - started)
    time_ms = statistics.median(passes) * 1000.0 / len(inputs)

    errors = np.sqrt(np.mean((predictions.astype(np.float64) - targets) ** 2, axis=1))
    values = []
    for index, error in enumerate(errors):
        case = f'test-{index:03d}'
        values.append({'case': case, 'metric': 'error', 'value': float(error)})
        values.append({'case': case, 'metric': 'time_ms', 'value': time_ms})

    document = {
        'format': 'tuldok_results_v1',
        'benchmark': 'held-out',
        'subject': arguments.name,
        'commit': '',  # Tuldok records the commit of the run itself
        'produced': datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
        'values': values,
    }
    with open(os.path.join(arguments.output, 'results.json'), 'w', encoding='utf-8') as handle:
        json.dump(document, handle, indent=1)
        handle.write('\n')
    print(f'{arguments.name}: median error {float(np.median(errors)):.4f}, {time_ms:.6f} ms per wave')


if __name__ == '__main__':
    main()
