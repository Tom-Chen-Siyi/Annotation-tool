from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from .config import IMAGE_DIR, JSON_DIR


def load_matched_pairs(
    image_dir: Path = IMAGE_DIR,
    json_dir: Path = JSON_DIR,
) -> List[Tuple[Path, Path]]:
    """
    Pair images with JSON files.

    Rule: an image matches the first JSON whose stem contains the image stem.
    """
    images = sorted([*image_dir.glob("*.jpg"), *image_dir.glob("*.png")])
    jsons = sorted(json_dir.glob("*.json"))

    matched: List[Tuple[Path, Path]] = []
    for img_path in images:
        img_key = img_path.stem
        best_match = None
        for js_path in jsons:
            if img_key in js_path.stem:
                best_match = js_path
                break
        if best_match:
            matched.append((img_path, best_match))

    return matched

