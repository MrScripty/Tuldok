"""Owned images in train/val/test/<class>/*.png. Torch 2.8.0/vision 0.23.0 API.
--backbone tiny: scratch CNN, no weight download.
--backbone mobilenet: downloads reviewed ImageNet weights; frozen feature extractor.
Syntax-checked only. Choose group-based splits before arranging folders.
"""
import argparse
import json
from pathlib import Path
import torch
from torch import nn
from torch.utils.data import DataLoader
from torchvision import datasets, transforms
from torchvision.models import mobilenet_v3_small, MobileNet_V3_Small_Weights
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix


class TinyCNN(nn.Module):
    def __init__(self, classes):
        super().__init__()
        self.net = nn.Sequential(nn.Conv2d(3, 16, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
                                 nn.Conv2d(16, 32, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
                                 nn.Conv2d(32, 64, 3, padding=1), nn.ReLU(),
                                 nn.AdaptiveAvgPool2d(1), nn.Flatten(), nn.Linear(64, classes))
    def forward(self, x):
        return self.net(x)


@torch.no_grad()
def evaluate(model, loader, device):
    model.eval(); loss_sum = 0.; truth, predicted = [], []
    for x, y in loader:
        logits = model(x.to(device)); loss_sum += float(nn.functional.cross_entropy(logits, y.to(device)))*len(x)
        truth.extend(y.tolist()); predicted.extend(logits.argmax(1).cpu().tolist())
    return {"loss": loss_sum/len(loader.dataset), "accuracy": accuracy_score(truth, predicted),
            "macro_f1": f1_score(truth, predicted, average="macro", labels=list(range(len(loader.dataset.classes))), zero_division=0),
            "confusion_matrix": confusion_matrix(truth, predicted, labels=list(range(len(loader.dataset.classes)))).tolist()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default="runs/image-classifier")
    ap.add_argument("--backbone", choices=["tiny", "mobilenet"], default="tiny")
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--lr", type=float, default=.001)
    ap.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    a = ap.parse_args(); torch.manual_seed(42)
    if a.epochs < 1 or a.batch_size < 1:
        ap.error("epochs and batch-size must be positive")
    weights = MobileNet_V3_Small_Weights.IMAGENET1K_V1
    preprocessing = weights.transforms() if a.backbone == "mobilenet" else transforms.Compose([
        transforms.Resize((96, 96)), transforms.ToTensor()])
    ds = {s: datasets.ImageFolder(Path(a.data)/s, transform=preprocessing) for s in ["train", "val", "test"]}
    if any(d.class_to_idx != ds["train"].class_to_idx for d in ds.values()):
        raise ValueError("Every split must have identical class folders")
    if len(ds["train"].classes) < 2:
        raise ValueError("Need at least two classes")
    loaders = {s: DataLoader(d, batch_size=a.batch_size, shuffle=(s == "train"), num_workers=0) for s, d in ds.items()}
    if a.backbone == "tiny":
        model = TinyCNN(len(ds["train"].classes))
    else:
        model = mobilenet_v3_small(weights=weights)
        for p in model.parameters():
            p.requires_grad_(False)
        model.classifier[-1] = nn.Linear(model.classifier[-1].in_features, len(ds["train"].classes))
    model.to(a.device)
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=a.lr, weight_decay=.0001)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True); best = float("inf"); history = []
    for epoch in range(a.epochs):
        model.train()
        if a.backbone == "mobilenet":
            # Frozen BatchNorm running statistics must not drift during head-only training.
            model.features.eval()
        for x, y in loaders["train"]:
            optimizer.zero_grad(set_to_none=True)
            loss = nn.functional.cross_entropy(model(x.to(a.device)), y.to(a.device))
            loss.backward(); optimizer.step()
        metrics = evaluate(model, loaders["val"], a.device); history.append({"epoch": epoch+1, **metrics})
        print(json.dumps(history[-1]))
        if metrics["loss"] < best:
            best = metrics["loss"]
            torch.save(model.state_dict(), out / "best.pt")
    model.load_state_dict(torch.load(out / "best.pt", map_location=a.device, weights_only=True))
    report = {"config": vars(a), "class_to_idx": ds["train"].class_to_idx, "history": history,
              "test": evaluate(model, loaders["test"], a.device), "torch": torch.__version__}
    (out / "metrics.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report["test"], indent=2))

if __name__ == "__main__":
    main()
