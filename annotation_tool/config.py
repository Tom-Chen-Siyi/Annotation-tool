from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List, Optional

# Project root (the directory containing pyqt_annotation_tool.py)
BASE_DIR = Path(__file__).resolve().parent.parent
PACKAGE_DIR = Path(__file__).resolve().parent

# Data folders
IMAGE_DIR = BASE_DIR / "sample_frames"
JSON_DIR = BASE_DIR / "sample_jsons"

# Debug logging (prints during drag/resize, etc.)
DEBUG = False

# Session persistence (last frame / bbox)
SESSION_STATE_PATH = BASE_DIR / ".annotation_tool_state.json"

# === Dropdown Options ===
_DEFAULT_CLASS_OPTIONS: List[str] = [
    "Person",
    "Bicycle",
    "Car",
    "Motorcycle",
    "Bus",
    "Train",
    "Truck",
    "Traffic Light",
    "Fire Hydrant",
    "Stop Sign",
    "Parking Meter",
    "Bench",
    "Dog",
    "Other",
]

_DEFAULT_DETAILED_CLASS_OPTIONS: List[str] = [
    "Car",
    "Pedestrian",
    "Bicycle",
    "Motorcycle",
    "Bus",
    "Train",
    "Traffic Light",
    "Green Traffic Light",
    "Yellow Traffic Light",
    "Red Traffic Light",
    "Fire Hydrant",
    "Stop sign",
    "Parking Meter",
    "Bench",
    "Bollard",
    "Construction Cone",
    "Construction Barrel",
    "Large Vehicle",
    "Box Truck",
    "Truck Cab",
    "Vehicular Trailer",
    "Truck",
    "Police Car",
    "Fire Truck",
    "Ambulance",
    "Sign",
    "Tree",
    "Animal",
    "School Bus",
    "Stroller",
    "Articulated Bus",
    "Message Board Trailer",
    "Mobile Pedestrian Sign",
    "Yield Sign",
    "Wheel Chair",
    "Wheeled Device",
    "Taxi",
    "Road Maintenance Vehicle",
    "Vehicle Signal",
    "Skateboard",
    "Traffic barricade",
    "Speed bump",
    "Road Personel",
]


CLASSES_JSON_PATH = PACKAGE_DIR / "classes.json"
CLASSES_DETAILED_JSON_PATH = PACKAGE_DIR / "classes_detailed.json"


def _dedupe_keep_order(items: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for s in items:
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _sort_case_insensitive(items: List[str]) -> List[str]:
    return sorted(items, key=lambda s: s.casefold())


def _load_string_list_from_json(path: Path, keys: Iterable[str]) -> Optional[List[str]]:
    """
    Load a list of strings from a JSON file.

    Supports multiple possible keys to tolerate naming changes.
    Returns None on any error or if not found.
    """
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        for k in keys:
            v = data.get(k)
            if isinstance(v, list) and all(isinstance(x, str) for x in v):
                cleaned = [x.strip() for x in v if x.strip()]
                return _dedupe_keep_order(cleaned)
        return None
    except Exception:
        return None


CLASS_OPTIONS: List[str] = (
    _load_string_list_from_json(CLASSES_JSON_PATH, keys=["classes", "class", "CLASS_OPTIONS"])
    or _DEFAULT_CLASS_OPTIONS
)
CLASS_OPTIONS = _sort_case_insensitive(CLASS_OPTIONS)

DETAILED_CLASS_OPTIONS: List[str] = (
    _load_string_list_from_json(
        CLASSES_DETAILED_JSON_PATH,
        keys=["classes detailed", "classes_detailed", "detailed_classes", "DETAILED_CLASS_OPTIONS"],
    )
    or _DEFAULT_DETAILED_CLASS_OPTIONS
)
DETAILED_CLASS_OPTIONS = _sort_case_insensitive(DETAILED_CLASS_OPTIONS)
