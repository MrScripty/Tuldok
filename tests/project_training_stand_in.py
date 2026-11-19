"""A stand-in training script for tests/browser_project_workspace_training.cjs: it trains nothing real.

A linear model of sixteen weights and a bias is fitted by gradient descent, in
plain Python on the CPU, to numbers it draws itself, and everything is logged
through tuldok_log as a project's script would: every step the loss, the
learning rate (a cosine schedule) and the gradient norm; every ten steps a
validation loss; every five steps the histograms of the weights and their
gradients (the model offers named_parameters, each parameter a list with a
grad); every ten steps two samples, the prediction over an 8 x 8 grid as an
.npy and as a small PNG. A tuldok_progress_v1 line is printed each step, and
--sleep slows it so that a run lasts a few seconds. At the end weights.json is
written, the recipe's declared output.

    python project_training_stand_in.py --out <output> [--steps 60] [--lr 0.05] [--sleep 0] [--seed 1]
"""
import argparse
import json
import math
import os
import random
import struct
import sys
import time
import zlib

from tuldok_log import Logger


class Parameter(list):
    grad = None


def png(rows):
    """A greyscale PNG of rows of values in 0..1."""
    height, width = len(rows), len(rows[0])
    raw = b''.join(b'\x00' + bytes(max(0, min(255, int(v * 255))) for v in row) for row in rows)

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    parser.add_argument('--steps', type=int, default=60)
    parser.add_argument('--lr', type=float, default=0.05)
    parser.add_argument('--sleep', type=float, default=0.0)
    parser.add_argument('--seed', type=int, default=1)
    options = parser.parse_args()
    rng = random.Random(options.seed)
    size = 16
    truth = [rng.gauss(0, 1) for _ in range(size)]
    inputs = [[rng.gauss(0, 1) for _ in range(size)] for _ in range(64)]
    targets = [sum(a * b for a, b in zip(x, truth)) + 0.5 for x in inputs]
    held_inputs = [[rng.gauss(0, 1) for _ in range(size)] for _ in range(16)]
    held_targets = [sum(a * b for a, b in zip(x, truth)) + 0.5 for x in held_inputs]
    weight = Parameter(rng.gauss(0, 0.1) for _ in range(size))
    bias = Parameter([0.0])

    class Model:
        @staticmethod
        def named_parameters():
            return [('linear.weight', weight), ('linear.bias', bias)]

    def predict(x):
        return sum(a * b for a, b in zip(x, weight)) + bias[0]

    log = Logger(options.out)
    for step in range(1, options.steps + 1):
        rate = options.lr * 0.5 * (1 + math.cos(math.pi * (step - 1) / options.steps))
        errors = [predict(x) - y for x, y in zip(inputs, targets)]
        loss = sum(e * e for e in errors) / len(errors)
        weight.grad = Parameter(2 * sum(e * x[i] for e, x in zip(errors, inputs)) / len(errors) for i in range(size))
        bias.grad = Parameter([2 * sum(errors) / len(errors)])
        norm = math.sqrt(sum(g * g for g in weight.grad) + bias.grad[0] ** 2)
        scalars = {'loss': loss, 'lr': rate, 'grad_norm': norm}
        if step % 10 == 0:
            scalars['val/loss'] = sum((predict(x) - y) ** 2 for x, y in zip(held_inputs, held_targets)) / 16
        log.log(step, epoch=step // 20, **scalars)
        if step % 5 == 0 or step == 1:
            log.log_histograms(step, Model(), bins=24)
        for i in range(size):
            weight[i] -= rate * weight.grad[i]
        bias[0] -= rate * bias.grad[0]
        if step % 10 == 0:
            grid = [[predict([math.sin(r + c * k / 3) for k in range(size)]) for c in range(8)] for r in range(8)]
            log.log_sample(step, 'field', grid)
            low = min(min(row) for row in grid)
            high = max(max(row) for row in grid)
            log.log_sample(step, 'prediction', png([[(v - low) / ((high - low) or 1) for v in row] for row in grid]))
        print(json.dumps({'format': 'tuldok_progress_v1', 'stage': 'fit', 'completed': step, 'total': options.steps,
                          'metrics': {'loss': loss}}), flush=True)
        if options.sleep:
            time.sleep(options.sleep)
    log.close()
    with open(os.path.join(options.out, 'weights.json'), 'w') as handle:
        json.dump({'weight': list(weight), 'bias': bias[0]}, handle)
    return 0


if __name__ == '__main__':
    sys.exit(main())
