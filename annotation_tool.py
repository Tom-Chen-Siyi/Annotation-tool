import os
import json
from pathlib import Path
from PIL import Image, ImageDraw
import matplotlib.pyplot as plt
from IPython.display import display
import ipywidgets as widgets
from PIL import ImageFont
import matplotlib.font_manager as fm

# === RESET STATE BEFORE EVERYTHING ELSE ===
for name in ['cache', 'idx', 'out', 'frame_info_label', 'matched_pairs']:
    if name in globals():
        del globals()[name]

# --- Configurable Parameters ---
image_dir = Path("sample_frames")          # Folder with .jpg/.png files
json_dir = Path("sample_jsons")      # Folder with .json annotation files
CACHE_WINDOW = 10                   # +/- frames around current to keep in cache
FONT_SIZE = 24

# --- Helper to Extract Frame Key from JSON Filename ---
def get_frame_key(json_name):
    return json_name.split("_")[0]

# --- Pair Images with JSONs ---
def load_matched_pairs():
    images = sorted([f for f in image_dir.glob("*.jpg")] + [f for f in image_dir.glob("*.png")])
    jsons = sorted([f for f in json_dir.glob("*.json")])

    matched = []

    for img_path in images:
        img_key = img_path.stem  # e.g., "frame_001_night"
        best_match = None
        for js_path in jsons:
            js_key = js_path.stem  # e.g., "frame_001_night_modelA"
            if img_key in js_key:  # JSON file "includes" the image identifier
                best_match = js_path
                break  # only take the first match
        if best_match:
            matched.append((img_path, best_match))

    return matched


matched_pairs = load_matched_pairs()
total_frames = len(matched_pairs)

if total_frames == 0:
    raise ValueError("No matched image/JSON pairs found. Please check your `image_dir` and `json_dir` paths and file formats.")

def load_display_font(size=50):
    try:
        # First try: Arial (only if uploaded or available)
        return ImageFont.truetype("arial.ttf", size)
    except:
        # Fallback: Use matplotlib's default font path
        font_path = fm.findfont(fm.FontProperties(family="DejaVu Sans"))
        return ImageFont.truetype(font_path, size)

# --- Caching ---
cache = {}

def load_and_cache(idx_val):
    global cache
    # Clear cache outside the window
    valid_range = range(max(0, idx_val - CACHE_WINDOW), min(total_frames, idx_val + CACHE_WINDOW + 1))
    for k in list(cache.keys()):
        if k not in valid_range:
            del cache[k]

    for i in valid_range:
        img_path, json_path = matched_pairs[i]

        # Always reload current index to ensure correct data
        if i == idx_val or i not in cache:
            with Image.open(img_path).convert("RGB") as img:
                draw = ImageDraw.Draw(img)
                with open(json_path, "r") as f:
                    annotations = json.load(f)
                    for ann in annotations:
                        box = ann["box"]
                        label = ann["class"]
                        score = ann.get("score", 1.0)
                        draw.rectangle(box, outline="red", width=3)
                        font = load_display_font(FONT_SIZE)
                        #draw.text((box[0], box[1] - 10), f"{label}", fill="yellow", font=font)
                # Cache a fresh copy
                cache[i] = (img.copy(), img_path.name, json_path.name)


# --- Display Widget Setup ---
idx = widgets.IntSlider(value=0, min=0, max=total_frames - 1, step=1, description="Frame")
frame_info_label = widgets.Label()
out = widgets.Output()

# --- Update Display ---
# Global to store current annotations
current_annotations = []
selected_index = widgets.IntText(value=-1, description="Selected Index:")

bbox_list = widgets.Select(options=[], rows=10, description='Boxes:')
class_input = widgets.Text(value='', description='New Class:')
rename_btn = widgets.Button(description="Rename")
delete_btn = widgets.Button(description="Delete")
save_btn = widgets.Button(description="Save JSON")
edit_out = widgets.Output()

def load_annotations(i):
    global current_annotations
    _, json_path = matched_pairs[i]
    with open(json_path, 'r') as f:
        current_annotations = json.load(f)
    bbox_list.options = [f"{idx}: {ann['class']} {ann['box']}" for idx, ann in enumerate(current_annotations)]
    selected_index.value = -1  # reset selection
    bbox_list.value = None      # clear listbox selection
    class_input.value = ''      # clear input


def on_idx_change(change):
    i = change['new']
    load_annotations(i)
    update_view()

def update_view(change=None):
    i = idx.value
    load_and_cache(i)  # loads and caches image only

    img, img_name, json_name = cache[i]

    out.clear_output(wait=True)
    frame_info_label.value = f"Frame: {img_name}, JSON: {json_name}"

    with out:
        draw_img = img.copy()
        draw = ImageDraw.Draw(draw_img)
        for j, ann in enumerate(current_annotations):
            box = ann["box"]
            label = ann["class"]
            outline_color = "blue" if j == selected_index.value else "red"
            draw.rectangle(box, outline=outline_color, width=4)
            font = load_display_font(FONT_SIZE)
            draw.text((box[0], box[1] - 10), f"{label} {j}", fill="yellow", font=font)

        plt.figure(figsize=(20, 15), dpi=100)
        plt.imshow(draw_img)
        plt.axis('off')
        plt.show()


def on_select(change):
    try:
        val = change['new']
        if val is None:
            selected_index.value = -1
            class_input.value = ''
            update_view()
            return
        index = int(val.split(":")[0])
        selected_index.value = index
        class_input.value = current_annotations[index]['class']
        update_view()
    except Exception as e:
        # Optionally print or log e for debugging
        pass


def on_rename(b):
    i = selected_index.value
    if 0 <= i < len(current_annotations):
        current_annotations[i]['class'] = class_input.value
        bbox_list.options = [f"{idx}: {ann['class']} {ann['box']}" for idx, ann in enumerate(current_annotations)]
        bbox_list.value = f"{i}: {current_annotations[i]['class']} {current_annotations[i]['box']}"
        update_view()


def on_delete(b):
    i = selected_index.value
    if 0 <= i < len(current_annotations):
        del current_annotations[i]
        selected_index.value = -1
        bbox_list.options = [f"{idx}: {ann['class']} {ann['box']}" for idx, ann in enumerate(current_annotations)]
        bbox_list.value = None  # force unselect
        update_view()

def on_save(b):
    _, json_path = matched_pairs[idx.value]
    with open(json_path, 'w') as f:
        json.dump(current_annotations, f, indent=2)

    # Flush image cache so updated boxes redraw correctly
    if idx.value in cache:
        del cache[idx.value]

    load_and_cache(idx.value)
    update_view()

    with edit_out:
        edit_out.clear_output()
        print(f"Saved and reloaded JSON: {json_path.name}")




bbox_list.observe(on_select, names='value')
rename_btn.on_click(on_rename)
delete_btn.on_click(on_delete)
save_btn.on_click(on_save)

edit_controls = widgets.VBox([
    bbox_list,
    widgets.HBox([class_input, rename_btn]),
    widgets.HBox([delete_btn, save_btn]),
    edit_out
])


# --- Navigation Buttons ---
prev_btn = widgets.Button(description="Previous", icon="arrow-left")
next_btn = widgets.Button(description="Next", icon="arrow-right")

def on_prev(b):
    if idx.value > 0:
        idx.value -= 1

def on_next(b):
    if idx.value < total_frames - 1:
        idx.value += 1

prev_btn.on_click(on_prev)
next_btn.on_click(on_next)

# --- Display UI ---
controls = widgets.HBox([prev_btn, next_btn, idx])
display(frame_info_label, controls, out)

idx.observe(on_idx_change, names='value')

load_annotations(idx.value)
update_view()
display(edit_controls)