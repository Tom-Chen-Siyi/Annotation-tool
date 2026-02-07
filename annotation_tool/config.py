from __future__ import annotations

from pathlib import Path

# Project root (the directory containing pyqt_annotation_tool.py)
BASE_DIR = Path(__file__).resolve().parent.parent

# Data folders
IMAGE_DIR = BASE_DIR / "sample_frames"
JSON_DIR = BASE_DIR / "sample_jsons"

# Debug logging (prints during drag/resize, etc.)
DEBUG = False

# Session persistence (last frame / bbox)
SESSION_STATE_PATH = BASE_DIR / ".annotation_tool_state.json"

# === Dropdown Options ===
CLASS_OPTIONS = [
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

DETAILED_CLASS_OPTIONS = [
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

