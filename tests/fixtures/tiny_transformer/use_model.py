"""Generate bytes or evaluate a held-out file from a trusted local checkpoint."""
import argparse
from pathlib import Path
import torch
from model import Config, ByteTransformer
from train import read_bytes, evaluate

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("checkpoint", type=Path)
p.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
p.add_argument("--prompt", default="Record item")
p.add_argument("--new-bytes", type=int, default=200)
p.add_argument("--temperature", type=float, default=0.8)
p.add_argument("--seed", type=int, default=42)
p.add_argument("--evaluate-file", type=Path)
a = p.parse_args()
if a.temperature <= 0 or a.new_bytes < 0:
    p.error("temperature must be positive and new-bytes nonnegative")
if a.device == "cuda" and not torch.cuda.is_available():
    p.error("CUDA requested but unavailable")
ck = torch.load(a.checkpoint, map_location=a.device, weights_only=True)
m = ByteTransformer(Config(**ck["run"]["model_config"])).to(a.device)
m.load_state_dict(ck["model"])
m.eval()
if a.evaluate_file:
    data, digest = read_bytes(a.evaluate_file)
    print({"sha256": digest, **evaluate(m, data, a.device, False, max_chunks=len(data))})
else:
    torch.manual_seed(a.seed)
    encoded = list(a.prompt.encode("utf-8"))
    if not encoded:
        p.error("prompt cannot be empty")
    ids = torch.tensor([encoded], dtype=torch.long, device=a.device)
    with torch.inference_mode():
        for _ in range(a.new_bytes):
            logits = m(ids[:, -m.config.context:])[:, -1, :] / a.temperature
            token = torch.multinomial(torch.softmax(logits, dim=-1), 1)
            ids = torch.cat([ids, token], dim=1)
    print(bytes(ids[0].tolist()).decode("utf-8", errors="replace"))
