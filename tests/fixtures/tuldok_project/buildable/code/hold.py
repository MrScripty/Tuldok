"""Hold "the GPU" for a moment and write when: the stand-in GPU step. It uses no GPU."""
import argparse
import json
import os
import time

parser = argparse.ArgumentParser()
parser.add_argument('--out', required=True)
arguments = parser.parse_args()
started = time.time()
time.sleep(float(os.environ.get('BUILDABLE_HOLD_SECONDS', '0.6')))
with open(os.path.join(arguments.out, 'times.json'), 'w', encoding='utf-8') as handle:
    json.dump({'started': started, 'ended': time.time(),
               'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES')}, handle)
