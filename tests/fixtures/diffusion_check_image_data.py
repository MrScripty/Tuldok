#!/usr/bin/env python3
"""Validate the book's local imagefolder tree before a long LoRA run.
Usage: python check_image_data.py data/my_style
Expects train/metadata.jsonl, val/metadata.jsonl, test/metadata.jsonl.
Each row: file_name, text, group. Each image is stored beside its metadata file.
The group field is retained by imagefolder and ignored by the trainer.
"""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageOps

def main():
    p=argparse.ArgumentParser(); p.add_argument("root",type=Path); a=p.parse_args()
    hashes, groups, count = {}, {}, 0
    for split in ("train","val","test"):
        path=a.root/split/"metadata.jsonl"
        rows=[json.loads(x) for x in path.read_text().splitlines() if x.strip()]
        if not rows: raise ValueError(f"Empty {split}")
        for row in rows:
            fn=a.root/split/row["file_name"]
            if not row.get("text","").strip(): raise ValueError(f"Empty caption: {fn}")
            if not row.get("group","").strip(): raise ValueError(f"Missing group: {fn}")
            if row["group"] in groups and groups[row["group"]]!=split:
                raise ValueError(f"Group crosses split: {row['group']}")
            groups[row["group"]]=split
            with Image.open(fn) as im:
                if im.getexif().get(274,1) != 1:
                    raise ValueError(f"Normalize EXIF orientation and save pixels before training: {fn}")
                im=ImageOps.exif_transpose(im).convert("RGB"); im.load()
                if min(im.size)<512: print(f"WARNING small image {fn}: {im.size}")
                digest=hashlib.sha256(str(im.size).encode()+im.tobytes()).hexdigest()
            if digest in hashes: raise ValueError(f"Exact duplicate: {fn}, {hashes[digest]}")
            hashes[digest]=str(fn); count+=1
        print(f"{split}: {len(rows)} readable RGB-convertible images, captions present")
    print(f"PASS: {count} records; no exact pixel duplicates or cross-split group leakage")
    print("Still inspect crops, near-duplicates, captions, rights and sensitive metadata manually")
if __name__=="__main__": main()
