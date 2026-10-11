"""CC0 authored tiny PNG corpus for real browser import/training mechanics.

Twelve independent drawings with unique pixels; not a model-quality dataset.
No network, copied data, pretrained weights or product-side fixture admission.
"""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw


def create(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(12):
        label = 'circle' if i % 2 else 'square'
        image = Image.new('RGB', (32, 28), (239 - i, 243 - i, 249 - i))
        draw = ImageDraw.Draw(image)
        shape = (7, 5, 24, 22)
        color = (60 + i * 3, 104 + i, 197 - i * 2)
        if label == 'circle':
            draw.ellipse(shape, fill=color)
        else:
            draw.rectangle(shape, fill=color)
        path = directory / f'authored-{i:02d}-{label}.png'
        image.save(path)
        rows.append({'path': str(path.resolve()), 'label': label, 'group': f'authored-independent-{i:02d}'})
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    print(json.dumps(create(parser.parse_args().output)))
