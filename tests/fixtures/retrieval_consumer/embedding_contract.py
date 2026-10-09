"""Pure-Python shared query formatting and model/index integrity helpers."""
import hashlib
from pathlib import Path

MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
MODEL_REVISION = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
DEFAULT_INSTRUCTION = "Given a support question, retrieve the help article that answers it for the correct product."


def format_query(text, instruction=DEFAULT_INSTRUCTION):
    if not text.strip() or not instruction.strip():
        raise ValueError("Query and instruction must be non-empty")
    # Exactly one instruction, only on queries. Documents remain unprefixed.
    return f"Instruct: {instruction.strip()}\nQuery:{text.strip()}"


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def model_fingerprint(root):
    root = Path(root)
    # Include weights, tokenizer, pooling, normalization and saved configuration.
    files = sorted(p for p in root.rglob("*") if p.is_file())
    if not files:
        raise ValueError("Saved model directory is empty")
    return {str(p.relative_to(root)): sha256_file(p) for p in files}
