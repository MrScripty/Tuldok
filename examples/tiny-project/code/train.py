"""Train SmallNet on the training waves and write model.pt and log.json.

Prints a tuldok_progress_v1 line every 50 updates so Tuldok can show how far
training has come while it runs.
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np
import torch

from net import SmallNet

EVERY = 50  # updates between progress lines and log entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', required=True, help='the waves.npz file')
    parser.add_argument('--settings', required=True, help='a JSON file: updates, batch, learning_rate, seed')
    parser.add_argument('--output', required=True, help='the directory to write model.pt and log.json into')
    # The recipe trains on the GPU. --device cpu exists only to smoke-test this
    # script on a machine without one; the recipe never passes it.
    parser.add_argument('--device', choices=['cuda', 'cpu'], default='cuda')
    arguments = parser.parse_args()

    if arguments.device == 'cuda' and not torch.cuda.is_available():
        # Refuse rather than fall back: a recipe that says it trains on the GPU
        # must not quietly produce a CPU model.
        sys.exit('train.py: CUDA is not available to torch, and this recipe trains on the GPU. '
                 'Check the gpu environment (tuldok_project check-environment), '
                 'or pass --device cpu to smoke-test the script by hand.')
    device = torch.device(arguments.device)
    if arguments.device == 'cpu':
        # A network this small runs fastest on one thread; on a many-core machine
        # torch's default thread pool makes it a hundred times slower.
        torch.set_num_threads(1)

    with open(arguments.settings, encoding='utf-8') as handle:
        settings = json.load(handle)
    updates, batch = int(settings['updates']), int(settings['batch'])

    # Same seed, same result: the weights are made on the CPU before moving, the
    # batches are drawn by a CPU generator, and the GPU is asked for
    # deterministic kernels (the recipe sets CUBLAS_WORKSPACE_CONFIG for cuBLAS).
    # warn_only keeps a run going if some kernel has no deterministic version.
    torch.manual_seed(settings['seed'])
    torch.use_deterministic_algorithms(True, warn_only=True)
    batches = torch.Generator().manual_seed(settings['seed'])

    with np.load(arguments.data) as waves:
        inputs = torch.from_numpy(waves['train_inputs']).to(device)
        targets = torch.from_numpy(waves['train_targets']).to(device)

    model = SmallNet().to(device)
    optimiser = torch.optim.Adam(model.parameters(), lr=float(settings['learning_rate']))
    loss_function = torch.nn.MSELoss()
    log = {'every': EVERY, 'updates': [], 'loss': []}

    started = time.perf_counter()
    for update in range(1, updates + 1):
        chosen = torch.randint(len(inputs), (batch,), generator=batches).to(device)
        loss = loss_function(model(inputs[chosen]), targets[chosen])
        optimiser.zero_grad(set_to_none=True)
        loss.backward()
        optimiser.step()
        if update % EVERY == 0 or update == updates:
            value = loss.item()  # waits for the GPU only here, not on every update
            if not math.isfinite(value):
                sys.exit(f'train.py: the loss became {value} at update {update}; stopping.')
            log['updates'].append(update)
            log['loss'].append(value)
            print(json.dumps({'format': 'tuldok_progress_v1', 'stage': 'train', 'completed': update,
                              'total': updates, 'metrics': {'loss': value}}), flush=True)
    log['seconds'] = time.perf_counter() - started
    log['device'] = arguments.device

    # Saved on the CPU so the weights load on any machine.
    torch.save({name: tensor.cpu() for name, tensor in model.state_dict().items()},
               os.path.join(arguments.output, 'model.pt'))
    with open(os.path.join(arguments.output, 'log.json'), 'w', encoding='utf-8') as handle:
        json.dump(log, handle, indent=1)
        handle.write('\n')
    print(f'trained {updates} updates in {log["seconds"]:.1f} s; final loss {log["loss"][-1]:.5f}')


if __name__ == '__main__':
    main()
