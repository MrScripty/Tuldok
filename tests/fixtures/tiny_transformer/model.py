"""Original small causal byte transformer. Reference API: torch==2.8.0."""
from dataclasses import dataclass
import torch
from torch import nn
from torch.nn import functional as F


@dataclass
class Config:
    context: int = 128
    width: int = 128
    layers: int = 4
    heads: int = 4
    dropout: float = 0.1
    vocab: int = 256


class Attention(nn.Module):
    def __init__(self, c):
        super().__init__()
        if c.width % c.heads:
            raise ValueError("width must be divisible by heads")
        self.heads, self.head_size, self.dropout = c.heads, c.width // c.heads, c.dropout
        self.qkv = nn.Linear(c.width, 3 * c.width, bias=False)
        self.projection = nn.Linear(c.width, c.width, bias=False)
        self.output_dropout = nn.Dropout(c.dropout)

    def forward(self, x):
        b, t, d = x.shape
        q, k, v = self.qkv(x).split(d, dim=-1)
        q, k, v = [z.view(b, t, self.heads, self.head_size).transpose(1, 2)
                   for z in (q, k, v)]
        y = F.scaled_dot_product_attention(
            q, k, v, is_causal=True,
            dropout_p=self.dropout if self.training else 0.0)
        y = y.transpose(1, 2).contiguous().view(b, t, d)
        return self.output_dropout(self.projection(y))


class Block(nn.Module):
    def __init__(self, c):
        super().__init__()
        self.norm1 = nn.LayerNorm(c.width)
        self.attention = Attention(c)
        self.norm2 = nn.LayerNorm(c.width)
        self.feed_forward = nn.Sequential(
            nn.Linear(c.width, 4 * c.width), nn.GELU(),
            nn.Linear(4 * c.width, c.width), nn.Dropout(c.dropout))

    def forward(self, x):
        x = x + self.attention(self.norm1(x))
        return x + self.feed_forward(self.norm2(x))


class ByteTransformer(nn.Module):
    def __init__(self, c):
        super().__init__()
        self.config = c
        self.token = nn.Embedding(c.vocab, c.width)
        self.position = nn.Embedding(c.context, c.width)
        self.blocks = nn.Sequential(*[Block(c) for _ in range(c.layers)])
        self.norm = nn.LayerNorm(c.width)
        self.head = nn.Linear(c.width, c.vocab, bias=False)
        self.apply(self._init)
        self.head.weight = self.token.weight  # tied input/output vocabulary weights

    @staticmethod
    def _init(module):
        if isinstance(module, (nn.Linear, nn.Embedding)):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
        if isinstance(module, nn.Linear) and module.bias is not None:
            nn.init.zeros_(module.bias)

    def forward(self, ids):
        if ids.ndim != 2 or ids.shape[1] > self.config.context:
            raise ValueError("expected [batch, time] with time <= context")
        positions = torch.arange(ids.shape[1], device=ids.device)
        x = self.token(ids) + self.position(positions)
        return self.head(self.norm(self.blocks(x)))
