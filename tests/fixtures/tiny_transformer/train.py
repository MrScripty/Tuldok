"""Train from random weights; no pretrained model or remote code is loaded.
Reference: Python 3.11, torch 2.8.0. Syntax checked; GPU execution untested.
"""
import argparse
from contextlib import nullcontext
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import time
import torch
from torch.nn import functional as F
from model import Config, ByteTransformer


def read_bytes(path):
    raw = path.read_bytes()
    return torch.tensor(list(raw), dtype=torch.long), hashlib.sha256(raw).hexdigest()


def batch(data, context, batch_size, generator, device):
    if len(data) <= context:
        raise ValueError("split must contain more bytes than context")
    starts = torch.randint(len(data) - context, (batch_size,), generator=generator)
    x = torch.stack([data[int(i):int(i) + context] for i in starts])
    y = torch.stack([data[int(i) + 1:int(i) + context + 1] for i in starts])
    return x.to(device), y.to(device)


def amp_context(device, bf16):
    return torch.autocast(device_type="cuda", dtype=torch.bfloat16) if bf16 else nullcontext()


@torch.no_grad()
def evaluate(model, data, device, bf16, max_chunks=64):
    previous = model.training
    model.eval()
    total, count = 0.0, 0
    context = model.config.context
    for start in range(0, min(len(data) - 1, max_chunks * context), context):
        n = min(context, len(data) - start - 1)
        x = data[start:start + n].unsqueeze(0).to(device)
        y = data[start + 1:start + n + 1].to(device)
        with amp_context(device, bf16):
            logits = model(x)[0]
            loss_sum = F.cross_entropy(logits.float(), y, reduction="sum")
        total += loss_sum.item()
        count += n
    model.train(previous)
    if not count:
        raise ValueError("evaluation split is empty")
    return {"loss_nats_per_byte": total / count,
            "bits_per_byte": total / count / math.log(2), "evaluated_bytes": count}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    p.add_argument("--steps", type=int, default=100)
    p.add_argument("--batch-size", type=int, default=4)
    p.add_argument("--accumulation", type=int, default=1)
    p.add_argument("--context", type=int, default=128)
    p.add_argument("--width", type=int, default=128)
    p.add_argument("--layers", type=int, default=4)
    p.add_argument("--heads", type=int, default=4)
    p.add_argument("--dropout", type=float, default=0.1)
    p.add_argument("--learning-rate", type=float, default=3e-4)
    p.add_argument("--weight-decay", type=float, default=0.1)
    p.add_argument("--warmup", type=int, default=10)
    p.add_argument("--eval-every", type=int, default=50)
    p.add_argument("--seed", type=int, default=1234)
    p.add_argument("--bf16", action="store_true")
    p.add_argument("--resume", type=Path)
    a = p.parse_args()
    positive = [a.steps, a.batch_size, a.accumulation, a.context, a.width, a.layers, a.heads, a.eval_every]
    if min(positive) < 1 or a.width % a.heads or a.learning_rate <= 0 or not 0 <= a.dropout < 1:
        p.error("invalid positive size, width/head division, rate, or dropout")
    if a.warmup < 0 or a.warmup >= a.steps:
        p.error("warmup must be >= 0 and less than steps")
    if a.device == "cuda" and not torch.cuda.is_available():
        p.error("CUDA requested but unavailable; no silent CPU fallback")
    if a.bf16 and (a.device != "cuda" or not torch.cuda.is_bf16_supported()):
        p.error("BF16 requires a compatible CUDA device")
    if a.output.exists() and any(a.output.iterdir()) and not a.resume:
        p.error("output is nonempty; use a new directory or explicit --resume")
    a.output.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(a.seed)
    generator = torch.Generator().manual_seed(a.seed + 1)
    train_data, train_hash = read_bytes(a.data / "train.txt")
    val_data, val_hash = read_bytes(a.data / "validation.txt")
    c = Config(a.context, a.width, a.layers, a.heads, a.dropout)
    model = ByteTransformer(c).to(a.device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=a.learning_rate,
        betas=(0.9, 0.95), eps=1e-8, weight_decay=a.weight_decay,
        foreach=False, fused=False)
    run = {k: str(v) if isinstance(v, Path) else v for k, v in vars(a).items()}
    run.update({"model_config": asdict(c), "torch_version": str(torch.__version__),
        "train_sha256": train_hash, "validation_sha256": val_hash,
        "parameters": sum(x.numel() for x in model.parameters()),
        "numeric_policy": "FP32 parameters and AdamW states; optional BF16 autocast"})
    start_step = 0
    if a.resume:
        ck = torch.load(a.resume, map_location=a.device, weights_only=True)
        for key in ["model_config", "train_sha256", "validation_sha256", "steps", "batch_size",
                    "accumulation", "learning_rate", "weight_decay", "warmup", "bf16", "device"]:
            if ck["run"][key] != run[key]:
                raise ValueError(f"resume mismatch: {key}")
        model.load_state_dict(ck["model"])
        optimizer.load_state_dict(ck["optimizer"])
        generator.set_state(ck["batch_rng"].cpu())
        torch.set_rng_state(ck["cpu_rng"].cpu())
        if a.device == "cuda":
            torch.cuda.set_rng_state_all([x.cpu() for x in ck["cuda_rng"]])
        start_step = ck["step"]
    (a.output / "run.json").write_text(json.dumps(run, indent=2) + "\n")
    print(json.dumps(run, indent=2))
    baseline = evaluate(model, val_data, a.device, a.bf16)
    print("validation_at_start", json.dumps(baseline))
    if a.device == "cuda":
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()
    started = time.perf_counter()
    log_path = a.output / "metrics.jsonl"
    for step in range(start_step, a.steps):
        if step < a.warmup:
            scale = (step + 1) / max(1, a.warmup)
        else:
            progress = (step - a.warmup) / max(1, a.steps - a.warmup - 1)
            scale = 0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * progress))
        for group in optimizer.param_groups:
            group["lr"] = a.learning_rate * scale
        model.train()
        optimizer.zero_grad(set_to_none=True)
        total_loss = 0.0
        for _ in range(a.accumulation):
            x, y = batch(train_data, a.context, a.batch_size, generator, a.device)
            with amp_context(a.device, a.bf16):
                logits = model(x)
                loss = F.cross_entropy(logits.float().reshape(-1, 256), y.reshape(-1))
            if not torch.isfinite(loss):
                raise FloatingPointError(f"nonfinite loss at update {step + 1}")
            (loss / a.accumulation).backward()
            total_loss += loss.item() / a.accumulation
        norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0, error_if_nonfinite=True)
        optimizer.step()
        if (step + 1) % a.eval_every == 0 or step + 1 == a.steps:
            row = {"step": step + 1, "training_loss": total_loss,
                   "learning_rate": optimizer.param_groups[0]["lr"],
                   "gradient_norm_before_clip": float(norm),
                   "validation": evaluate(model, val_data, a.device, a.bf16)}
            if a.device == "cuda":
                torch.cuda.synchronize()
                row["peak_allocated_gib"] = torch.cuda.max_memory_allocated() / 1024**3
                row["peak_reserved_gib"] = torch.cuda.max_memory_reserved() / 1024**3
            elapsed = time.perf_counter() - started
            row["elapsed_seconds_including_eval"] = elapsed
            row["training_bytes_per_second_including_eval"] = (
                (step + 1 - start_step) * a.batch_size * a.context * a.accumulation / elapsed)
            print(json.dumps(row))
            with log_path.open("a") as f:
                f.write(json.dumps(row) + "\n")
            state = {"model": model.state_dict(), "optimizer": optimizer.state_dict(),
                     "run": run, "step": step + 1, "batch_rng": generator.get_state(),
                     "cpu_rng": torch.get_rng_state(),
                     "cuda_rng": torch.cuda.get_rng_state_all() if a.device == "cuda" else []}
            temporary = a.output / "checkpoint.tmp"
            torch.save(state, temporary)
            temporary.replace(a.output / "checkpoint.pt")
    print("Saved", a.output / "checkpoint.pt")


if __name__ == "__main__":
    main()
