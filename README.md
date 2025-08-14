# PyQt Image Annotation Tool

A professional desktop application for viewing and editing image annotations with interactive bounding box manipulation.

## Features

- **Interactive Bounding Box Editing**: Drag and drop bounding boxes and resize handles
- **Zoom and Pan**: Mouse wheel zoom centered on click position, drag to pan image
- **Real-time Coordinate Sync**: Changes are immediately reflected in the UI
- **Multi-frame Support**: Navigate through multiple image frames
- **JSON Export**: Export annotations to JSON format
- **Professional UI**: Clean, responsive interface with English labels

## Installation & Setup

### Prerequisites

- **Python 3.7+** installed on your system
- **Operating System**: macOS 10.14+ or Windows 10+

### Step 1: Install Python Dependencies

#### For MacBook Users:

```bash
# Install required packages
pip3 install PyQt5 Pillow numpy opencv-python

```

#### For Windows Users:

```cmd
# Install required packages
pip install PyQt5 Pillow numpy opencv-python
```

### Step 2: Download and Setup

1. **Download** the `pyqt_annotation_tool.py` file
2. **Create** the following directory structure(If not existed):

```
annotation-tool/
├── pyqt_annotation_tool.py
├── sample_frames/          # Put your image files here (.jpg, .png)
└── sample_jsons/           # Put your JSON files here (.json)
```

### Step 3: Prepare Your Data

#### Image Files:

- Place your images in the `sample_frames/` folder
- Supported formats: JPG, PNG, BMP, TIFF, GIF

#### JSON Files:

- Place your annotation files in the `sample_jsons/` folder
- **Important**: JSON filename must contain the image filename
- Example: `frame_001.jpg` ↔ `frame_001.json` or `frame_001_annotations.json`

#### JSON Format:

```json
[
  {
    "class": "person",
    "box": [x1, y1, x2, y2],
    "score": 0.95
  }
]
```

### Step 4: Run the Application

#### For MacBook Users:

```bash
python3 pyqt_annotation_tool.py
```

#### For Windows Users:

```cmd
python pyqt_annotation_tool.py
```
## File Naming Examples
Image file name must included in the json file name

| Image File      | JSON File                    | Status     |
| --------------- | ---------------------------- | ---------- |
| `frame_001.jpg` | `frame_001.json`             | ✅ Valid   |
| `frame_001.jpg` | `frame_001_annotations.json` | ✅ Valid   |
| `frame_001.jpg` | `frame_002.json`             | ❌ Invalid |
| `image1.png`    | `image1_modelA.json`         | ✅ Valid   |

## Usage

### Basic Controls:

- **Navigation**: Use arrow buttons or slider to switch frames
- **Zoom**: Mouse wheel or trackpad pinch
- **Pan**: Click and drag on empty image area
- **Reset Zoom**: Double-click on image

### Bounding Box Editing:

- **Select**: Click on bounding box (turns blue when selected)
- **Move**: Click and drag the box body
- **Resize**: Drag yellow handles at corners
- **Add**: Click "Add" button in right panel
- **Delete**: Select box and click "Delete" button

### Real-time Editing:

- **Coordinates**: Edit X1, Y1, X2, Y2 values in the right panel
- **Class**: Change annotation class name
- **Save**: Click "Save" to save current frame
- **Export**: Click "Export JSON" to export all frames

## Troubleshooting

### Common Issues:

#### "No matching image/JSON file pairs found"

- Ensure JSON filename contains the image filename
- Check that both `sample_frames/` and `sample_jsons/` directories exist
- Verify JSON format is correct

#### "python command not found"

- Install Python from [python.org](https://www.python.org/downloads/)
- Ensure "Add Python to PATH" is checked during installation

#### Poor performance with large images

- Reduce image resolution
- Close other applications
- Use smaller batch sizes


