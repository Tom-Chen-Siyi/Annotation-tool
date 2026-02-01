## PyQt Image Annotation Tool

Desktop app for browsing image frames and editing bounding-box annotations stored in JSON.

### Features

- **Interactive bbox editing**: click to select, drag to move, drag corner handles to resize.
- **Zoom & pan**: mouse wheel to zoom (centered on last click), drag empty area to pan, double-click to reset zoom.
- **Multi-frame navigation**: slider + buttons + direct frame index input.
- **Fast bbox navigation**: A/D switch bboxes; automatically jumps across frames (skipping empty frames).
- **Shortcut delete**: Delete/Backspace deletes the selected bbox.
- **Auto-save**: any bbox change (class / class detailed / caption / coordinates / drag / add / delete) is automatically saved to JSON; switching frames never asks.

### Project layout

Put images and JSON files in these folders (relative to the script):

```
Modify-annotation/
├── pyqt_annotation_tool.py
├── sample_frames/   # .jpg / .png
└── sample_jsons/    # .json
```

### File matching rule

The app pairs an image with a JSON file when the **image stem** is contained in the **JSON stem**.

Examples:

| Image file | JSON file | Status |
| --- | --- | --- |
| `frame_001.jpg` | `frame_001.json` | ✅ |
| `frame_001.jpg` | `frame_001_yolo11x_classified.json` | ✅ |
| `frame_001.jpg` | `frame_002.json` | ❌ |

### Annotation JSON format

Each JSON file is a list of objects like:

```json
[
  {
    "class": "car",
    "class_detailed": "police car",
    "detailed_caption": "a car parked on the right side",
    "box": [x1, y1, x2, y2],
    "score": 0.95
  }
]
```

Only `class` and `box` are required. Extra keys are preserved (except legacy `openvocab`, which is removed on save).

### Installation

#### Requirements

- Python 3.8+
- PyQt5
- Pillow

Install:

```bash
pip install PyQt5 Pillow
```

### Run

```bash
python3 pyqt_annotation_tool.py
```

### How to use

#### Frame navigation

- **Buttons**: `←` / `→` switch to previous/next frame.
- **Slider**: drag the progress slider to move through frames.
- **Index input**: type a 1-based frame index (the numerator) to jump directly.

#### Bounding boxes

- **Auto-select on launch**: opens on frame 1 and selects bbox 1 (if available).
- **Select**: click a bbox on the image or click the row in `BBox List`.
- **Move/resize**:
  - drag bbox body to move
  - drag corner handles to resize
- **Edit fields** (right panel):
  - `Class`, `Class Detailed`, `Detailed Caption`
  - `Top Left X/Y`, `Bottom Right X/Y`

#### Keyboard shortcuts

- **A**: previous bbox  
  - if currently at the first bbox of a frame, jumps to the **previous frame’s last bbox** (skips empty frames)
- **D**: next bbox  
  - if currently at the last bbox of a frame, jumps to the **next frame’s first bbox** (skips empty frames)
- **Delete / Backspace**: delete selected bbox (no confirmation)

#### Saving behavior

- **Auto-save is on**: changes are written to the current frame’s JSON automatically (debounced).
- **No “unsaved changes” prompts** when switching frames.

### Troubleshooting

- **“No matching image/JSON file pairs found”**
  - Ensure `sample_frames/` and `sample_jsons/` exist
  - Ensure each JSON filename contains the matching image filename stem
  - Ensure JSON files contain a valid list
