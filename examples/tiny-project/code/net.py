"""The small network that models/small-net names: 64 samples in, 16 samples out."""
from torch import nn


class SmallNet(nn.Sequential):
    def __init__(self, seen=64, hidden=256, ahead=16):
        super().__init__(
            nn.Linear(seen, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, ahead),
        )
