"""Writes the model graphs the structure checks read: tests/fixtures/model_graph/parent.json and derived.json.

Run once, with a Python that has PyTorch (the CPU is enough), and commit what it writes; the browser check
(tests/browser_project_workspace_structure.cjs) and the reader's tests read the committed files and need no
PyTorch:

    PYTHONPATH=. <python with torch> tests/project_structure_fixture_export.py

Both models are Net below, exported by tuldok_log.graph.export_graph on one example input of shape
(2, 1, 8, 8): a convolution stem, two residual blocks of two convolutions with an add, and an MLP head. The
derived model widens the head's hidden layer from 8 to 16 (head.0 and head.2 change shape) and adds a module
gate after the head.
"""
import os
import sys

import torch
from torch import nn

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tuldok_log.graph import export_graph  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'model_graph')


class Block(nn.Module):
    def __init__(self, width):
        super().__init__()
        self.conv1 = nn.Conv2d(width, width, 3, padding=1)
        self.act = nn.SiLU()
        self.conv2 = nn.Conv2d(width, width, 3, padding=1)

    def forward(self, x):
        return x + self.conv2(self.act(self.conv1(x)))


class Net(nn.Module):
    def __init__(self, hidden=8, gate=False):
        super().__init__()
        self.stem = nn.Conv2d(1, 4, 3, padding=1)
        self.blocks = nn.Sequential(Block(4), Block(4))
        self.head = nn.Sequential(nn.Linear(4, hidden), nn.SiLU(), nn.Linear(hidden, 3))
        self.gate = nn.Linear(3, 3) if gate else None

    def forward(self, x):
        y = self.head(self.blocks(self.stem(x)).mean((2, 3)))
        return y if self.gate is None else y * torch.sigmoid(self.gate(y))


def main():
    os.makedirs(OUT, exist_ok=True)
    torch.manual_seed(0)
    example = torch.zeros(2, 1, 8, 8)
    for name, model in (('parent', Net()), ('derived', Net(hidden=16, gate=True))):
        written = export_graph(model.eval(), example, os.path.join(OUT, name + '.json'))
        print(name, written['method'], written['complete'], len(written['nodes']), 'nodes')


if __name__ == '__main__':
    main()
