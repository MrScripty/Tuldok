"""Write waves.npz: noisy sine waves to read, and the clean continuation to predict.

Every wave has its own amplitude, frequency and phase, so a model has to read
them from the 64 noisy samples it is given before it can continue the wave.
"""
import argparse
import os

import numpy as np

SEEN = 64        # noisy samples a model reads
AHEAD = 16       # clean samples it must predict
NOISE = 0.1      # standard deviation of the noise on the samples it reads
COUNTS = {'train': 4000, 'test': 400}


def waves(generator, count):
    amplitude = generator.uniform(0.5, 2.0, size=(count, 1))
    # Radians per sample: periods from about 16 to 125 samples, so every input
    # holds at least half a period and the task is never hopeless.
    frequency = generator.uniform(0.05, 0.4, size=(count, 1))
    phase = generator.uniform(0.0, 2.0 * np.pi, size=(count, 1))
    clean = amplitude * np.sin(frequency * np.arange(SEEN + AHEAD) + phase)
    noisy = clean[:, :SEEN] + generator.normal(0.0, NOISE, size=(count, SEEN))
    return noisy.astype(np.float32), clean[:, SEEN:].astype(np.float32)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, help='the directory to write waves.npz into')
    parser.add_argument('--seed', type=int, required=True)
    arguments = parser.parse_args()

    # One generator drawn in a fixed order: the same seed gives the same file.
    generator = np.random.default_rng(arguments.seed)
    arrays = {}
    for split, count in COUNTS.items():
        arrays[f'{split}_inputs'], arrays[f'{split}_targets'] = waves(generator, count)
    path = os.path.join(arguments.output, 'waves.npz')
    np.savez(path, **arrays)
    print(f'wrote {path}: ' + ', '.join(f'{count} {split}' for split, count in COUNTS.items()))


if __name__ == '__main__':
    main()
