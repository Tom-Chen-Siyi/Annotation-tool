import sys
import json
from pathlib import Path
from typing import Optional
from PIL import Image
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QSlider, QListWidget,
                             QLineEdit, QSpinBox, QMessageBox, QGroupBox,
                             QGridLayout, QSplitter, QFrame, QTextEdit, QShortcut)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QFont

# === Configuration Parameters ===
image_dir = Path("sample_frames")
json_dir = Path("sample_jsons")
DEBUG = False

# === File Matching Functions ===
def load_matched_pairs():
    images = sorted([f for f in image_dir.glob("*.jpg")] + [f for f in image_dir.glob("*.png")])
    jsons = sorted([f for f in json_dir.glob("*.json")])

    matched = []
    for img_path in images:
        img_key = img_path.stem
        best_match = None
        for js_path in jsons:
            js_key = js_path.stem
            if img_key in js_key:
                best_match = js_path
                break
        if best_match:
            matched.append((img_path, best_match))

    return matched

# === Image Display Widget ===
class ImageDisplayWidget(QWidget):
    bbox_clicked = pyqtSignal(int)  # Send bounding box index
    bbox_modified = pyqtSignal(int)  # Send modified bounding box index
    zoom_changed = pyqtSignal(float)  # Send zoom scale
    
    def __init__(self):
        super().__init__()
        self.image = None
        self.annotations = []
        self.selected_bbox = -1
        self.scale_factor = 1.0
        self.original_size = None
        self.dragging = False
        self.drag_start_pos = None
        self.drag_bbox_index = -1
        self.drag_mode = "move"  # "move", "resize", "pan"
        self.resize_handle = None  # Resize handle position
        self.zoom_offset_x = 0  # Zoom offset
        self.zoom_offset_y = 0
        self.panning = False  # Whether currently panning image
        self.pan_start_pos = None  # Pan start position
        self.last_click_pos = None  # Record last click position
        self.handle_click_stats = {"total": 0, "detected": 0}  # Handle click statistics
        self.setMouseTracking(True)
        self.setMinimumSize(1200, 800)  # Further increase minimum size
        
    def set_image(self, image_path):
        """Set image"""
        self.image = QPixmap(str(image_path))
        self.original_size = self.image.size()
        self.update()
        
    def set_annotations(self, annotations):
        """Set annotation data"""
        self.annotations = annotations
        self.update()
        
    def set_selected_bbox(self, index):
        """Set selected bounding box"""
        self.selected_bbox = index
        self.update()
        
    def set_zoom(self, scale_factor):
        """Set zoom scale factor"""
        self.scale_factor = scale_factor
        self.update()
        

        
    def widget_to_image_coords(self, pos):
        """Convert widget coordinates to image coordinates"""
        if not self.image:
            return 0, 0
            
        widget_size = self.size()
        image_size = self.image.size()
        
        # Calculate scaling and offset (using current scale factor)
        scale_x = widget_size.width() / image_size.width()
        scale_y = widget_size.height() / image_size.height()
        auto_scale = min(scale_x, scale_y, 1.0)
        
        # Use custom scale or auto scale
        if self.scale_factor == 1.0:
            self.scale_factor = auto_scale
            
        scale_factor = self.scale_factor
        
        scaled_width = int(image_size.width() * scale_factor)
        scaled_height = int(image_size.height() * scale_factor)
        x_offset = (widget_size.width() - scaled_width) // 2 + self.zoom_offset_x
        y_offset = (widget_size.height() - scaled_height) // 2 + self.zoom_offset_y
        
        # Convert to image coordinates
        image_x = (pos.x() - x_offset) / scale_factor
        image_y = (pos.y() - y_offset) / scale_factor
        
        return image_x, image_y
        
    def mouseMoveEvent(self, event):
        """Mouse move event - handle dragging and panning"""
        # Handle bounding box dragging
        if self.dragging and self.drag_bbox_index >= 0 and self.drag_bbox_index < len(self.annotations):
            current_pos = event.pos()
            if self.drag_start_pos:
                # Calculate movement distance
                dx = current_pos.x() - self.drag_start_pos.x()
                dy = current_pos.y() - self.drag_start_pos.y()
                
                # Convert to image coordinate movement distance
                image_dx = dx / self.scale_factor
                image_dy = dy / self.scale_factor
                

                
                # Update bounding box coordinates
                bbox = self.annotations[self.drag_bbox_index]
                old_box = bbox["box"]
                
                if self.drag_mode == "move":
                    # Move mode
                    new_box = [
                        int(float(old_box[0]) + image_dx),
                        int(float(old_box[1]) + image_dy),
                        int(float(old_box[2]) + image_dx),
                        int(float(old_box[3]) + image_dy)
                    ]
                else:
                    # Resize mode
                    new_box = list(old_box)
                    try:
                        if self.resize_handle == "bottom_right":
                            new_box[2] = int(float(old_box[2]) + image_dx)
                            new_box[3] = int(float(old_box[3]) + image_dy)
                        elif self.resize_handle == "top_left":
                            new_box[0] = int(float(old_box[0]) + image_dx)
                            new_box[1] = int(float(old_box[1]) + image_dy)
                        elif self.resize_handle == "top_right":
                            new_box[2] = int(float(old_box[2]) + image_dx)
                            new_box[1] = int(float(old_box[1]) + image_dy)
                        elif self.resize_handle == "bottom_left":
                            new_box[0] = int(float(old_box[0]) + image_dx)
                            new_box[3] = int(float(old_box[3]) + image_dy)
                    except (ValueError, TypeError) as e:
                        # If coordinate conversion fails, keep original values
                        if DEBUG:
                            print(f"Coordinate conversion error: {e}")
                        new_box = list(old_box)
                
                # Ensure bounding box is valid and within image bounds
                widget_size = self.size()
                image_size = self.image.size()
                
                if DEBUG:
                    print(f"New bounding box: {new_box}")
                    print(f"Image size: {image_size.width()} x {image_size.height()}")
                
                # Check if bounding box is valid
                is_valid_size = len(new_box) == 4
                is_valid_coords = new_box[0] < new_box[2] and new_box[1] < new_box[3]
                is_in_bounds = (new_box[0] >= 0 and new_box[1] >= 0 and 
                               new_box[2] <= image_size.width() and new_box[3] <= image_size.height())
                
                if DEBUG:
                    print(f"BBox validation: size_valid={is_valid_size}, coords_valid={is_valid_coords}, in_bounds={is_in_bounds}")
                
                if is_valid_size and is_valid_coords and is_in_bounds:
                    try:
                        bbox["box"] = new_box
                        self.update()
                        
                        # Send signal to notify main window to update input fields
                        self.bbox_clicked.emit(self.drag_bbox_index)
                        # Notify main window that bbox data changed (for autosave / list refresh)
                        self.bbox_modified.emit(self.drag_bbox_index)
                        if DEBUG:
                            print(f"✅ Bounding box updated successfully")
                    except Exception as e:
                        if DEBUG:
                            print(f"❌ Bounding box update failed: {e}")
                else:
                    if DEBUG:
                        print(f"❌ Invalid bounding box: size={len(new_box)}, coords={new_box}")
                        if not is_valid_coords:
                            print(f"   Coordinate issue: x1({new_box[0]}) >= x2({new_box[2]}) or y1({new_box[1]}) >= y2({new_box[3]})")
                        if not is_in_bounds:
                            print(f"   Range issue: out of image bounds")
                        print(f"=== Drag debug end ===\n")
                
                # Update start position
                self.drag_start_pos = current_pos
        
        # Handle image panning
        elif self.panning and self.pan_start_pos:
            current_pos = event.pos()
            dx = current_pos.x() - self.pan_start_pos.x()
            dy = current_pos.y() - self.pan_start_pos.y()
            
            # Calculate new offset
            new_offset_x = self.zoom_offset_x + dx
            new_offset_y = self.zoom_offset_y + dy
            
            # Limit panning range to prevent image from being dragged out of view
            widget_size = self.size()
            image_size = self.image.size()
            
            # Calculate image size at current zoom level
            scale_x = widget_size.width() / image_size.width()
            scale_y = widget_size.height() / image_size.height()
            auto_scale = min(scale_x, scale_y, 1.0)
            current_scale = self.scale_factor if self.scale_factor != 1.0 else auto_scale
            
            scaled_width = int(image_size.width() * current_scale)
            scaled_height = int(image_size.height() * current_scale)
            
            # Calculate maximum allowed offset
            max_offset_x = max(0, (scaled_width - widget_size.width()) // 2)
            max_offset_y = max(0, (scaled_height - widget_size.height()) // 2)
            
            # Apply boundary constraints
            if scaled_width > widget_size.width():
                self.zoom_offset_x = max(-max_offset_x, min(max_offset_x, new_offset_x))
            else:
                self.zoom_offset_x = 0
                
            if scaled_height > widget_size.height():
                self.zoom_offset_y = max(-max_offset_y, min(max_offset_y, new_offset_y))
            else:
                self.zoom_offset_y = 0
            
            # Update start position
            self.pan_start_pos = current_pos
            
            # Redraw
            self.update()
                
    def mouseReleaseEvent(self, event):
        """Mouse release event - end dragging and panning"""
        if event.button() == Qt.LeftButton:
            self.dragging = False
            self.drag_start_pos = None
            self.drag_bbox_index = -1
            self.drag_mode = "move"
            self.resize_handle = None
            
            # End panning
            if self.panning:
                self.panning = False
                self.pan_start_pos = None
                self.setCursor(Qt.ArrowCursor)  # Restore default cursor
            
    def mouseDoubleClickEvent(self, event):
        """Mouse double-click event - reset zoom"""
        if event.button() == Qt.LeftButton:
            self.scale_factor = 1.0
            self.zoom_offset_x = 0
            self.zoom_offset_y = 0
            self.update()
            self.zoom_changed.emit(1.0)
            
    def wheelEvent(self, event):
        """Mouse wheel event - zoom functionality"""
        if self.image:
            # Get wheel angle
            delta = event.angleDelta().y()
            
            # Use last click position as zoom center, if not available use current mouse position
            zoom_center_pos = self.last_click_pos if self.last_click_pos else event.pos()
            
            # Calculate zoom factor
            if delta > 0:
                # Scroll up, zoom in
                new_scale = min(5.0, self.scale_factor * 1.1)
            else:
                # Scroll down, zoom out
                new_scale = max(0.1, self.scale_factor * 0.9)
            
            # Calculate zoom center position on image (before zoom)
            widget_size = self.size()
            image_size = self.image.size()
            
            # Calculate offset at current zoom level
            scale_x = widget_size.width() / image_size.width()
            scale_y = widget_size.height() / image_size.height()
            auto_scale = min(scale_x, scale_y, 1.0)
            
            current_scale = self.scale_factor if self.scale_factor != 1.0 else auto_scale
            scaled_width = int(image_size.width() * current_scale)
            scaled_height = int(image_size.height() * current_scale)
            x_offset = (widget_size.width() - scaled_width) // 2 + self.zoom_offset_x
            y_offset = (widget_size.height() - scaled_height) // 2 + self.zoom_offset_y
            
            # Zoom center position on image
            center_x = (zoom_center_pos.x() - x_offset) / current_scale
            center_y = (zoom_center_pos.y() - y_offset) / current_scale
            
            # Update zoom
            old_scale = self.scale_factor
            self.scale_factor = new_scale
            
            # Calculate new offset to keep mouse position unchanged
            new_scaled_width = int(image_size.width() * new_scale)
            new_scaled_height = int(image_size.height() * new_scale)
            new_x_offset = (widget_size.width() - new_scaled_width) // 2
            new_y_offset = (widget_size.height() - new_scaled_height) // 2
            
            # Calculate required offset to keep image point under zoom center unchanged
            self.zoom_offset_x = center_x * new_scale - zoom_center_pos.x() + new_x_offset
            self.zoom_offset_y = center_y * new_scale - zoom_center_pos.y() + new_y_offset
            
            # Update display
            self.update()
            
            # Send zoom signal
            self.zoom_changed.emit(new_scale)
        
    def paintEvent(self, event):
        """Paint event"""
        if self.image is None:
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Calculate scaling and centering
        widget_size = self.size()
        image_size = self.image.size()
        
        # Calculate scale factor (supports custom scaling)
        scale_x = widget_size.width() / image_size.width()
        scale_y = widget_size.height() / image_size.height()
        auto_scale = min(scale_x, scale_y, 1.0)
        
        # Use custom scale or auto scale
        if self.scale_factor == 1.0:
            current_scale = auto_scale
        else:
            current_scale = self.scale_factor
        
        # Calculate center position (considering zoom offset)
        scaled_width = int(image_size.width() * current_scale)
        scaled_height = int(image_size.height() * current_scale)
        x_offset = (widget_size.width() - scaled_width) // 2 + self.zoom_offset_x
        y_offset = (widget_size.height() - scaled_height) // 2 + self.zoom_offset_y
        
        # Draw image
        painter.drawPixmap(int(x_offset), int(y_offset), scaled_width, scaled_height, self.image)
        
        # Draw bounding boxes
        for i, ann in enumerate(self.annotations):
            box = ann["box"]
            label = ann["class"]
            
            # Scale coordinates (ensure coordinates are numeric types)
            x1 = int(float(box[0]) * current_scale) + x_offset
            y1 = int(float(box[1]) * current_scale) + y_offset
            x2 = int(float(box[2]) * current_scale) + x_offset
            y2 = int(float(box[3]) * current_scale) + y_offset
            

            
            # Draw rectangle - only selected bounding boxes have fill
            if i == self.selected_bbox:
                # Selected bounding box: blue border, semi-transparent blue fill
                painter.setPen(QPen(QColor(0, 0, 255), 3))
                painter.setBrush(QColor(0, 0, 255, 50))  # Semi-transparent blue fill
            else:
                # Regular bounding box: red border, no fill
                painter.setPen(QPen(QColor(255, 0, 0), 2))
                painter.setBrush(Qt.NoBrush)  # No fill
            
            painter.drawRect(int(x1), int(y1), int(x2 - x1), int(y2 - y1))
            
            # No visible corner handles for selected bbox (resize still works by dragging corners)
            
            # Draw label
            font = QFont("Arial", 12)  # 将字体大小从10增加到14
            painter.setFont(font)
            painter.setPen(QPen(QColor(255, 255, 0), 1))
            
            # Only show class and index (OpenVocab removed)
            display_text = f"{label} {i}"
            
            # Label background
            text_rect = painter.fontMetrics().boundingRect(display_text)
            painter.fillRect(int(x1), int(y1 - text_rect.height() - 5), 
                           text_rect.width() + 10, text_rect.height() + 5, 
                           QColor(0, 0, 0, 180))
            
            # Draw text
            painter.drawText(int(x1 + 5), int(y1 - 5), display_text)
    
    def mousePressEvent(self, event):
        """Mouse click event"""
        if event.button() == Qt.LeftButton and self.image:
            # Get click position
            pos = event.pos()
            image_x, image_y = self.widget_to_image_coords(pos)
            
            # Check if clicked on bounding box or resize handle
            bbox_clicked = False
            for i, ann in enumerate(self.annotations):
                box = ann["box"]
                # Ensure coordinates are numeric types for comparison
                if (float(box[0]) <= image_x <= float(box[2]) and 
                    float(box[1]) <= image_y <= float(box[3])):
                    
                    # Check if clicked on resize handle
                    handle_size = 16  # Further increase handle detection area to improve detection success rate
                    
                    # Count clicks
                    self.handle_click_stats["total"] += 1
                    
                    # Calculate handle position in window coordinates (consistent with drawing code)
                    widget_size = self.size()
                    image_size = self.image.size()
                    
                    # Use same scaling calculation as drawing code
                    scale_x = widget_size.width() / image_size.width()
                    scale_y = widget_size.height() / image_size.height()
                    auto_scale = min(scale_x, scale_y, 1.0)
                    
                    # Use custom scale or auto scale (consistent with drawing code)
                    if self.scale_factor == 1.0:
                        current_scale = auto_scale
                    else:
                        current_scale = self.scale_factor
                    
                    scaled_width = int(image_size.width() * current_scale)
                    scaled_height = int(image_size.height() * current_scale)
                    x_offset = (widget_size.width() - scaled_width) // 2 + self.zoom_offset_x
                    y_offset = (widget_size.height() - scaled_height) // 2 + self.zoom_offset_y
                    
                    # Calculate bounding box position in window coordinates
                    bbox_x1 = int(float(box[0]) * current_scale) + x_offset
                    bbox_y1 = int(float(box[1]) * current_scale) + y_offset
                    bbox_x2 = int(float(box[2]) * current_scale) + x_offset
                    bbox_y2 = int(float(box[3]) * current_scale) + y_offset
                    
                    # Check click position
                    mouse_x = event.pos().x()
                    mouse_y = event.pos().y()
                    
                    # Check four corner handles (using larger detection area)
                    
                    # Calculate handle center positions (consistent with drawing positions)
                    handle_centers = {
                        "top_left": (bbox_x1, bbox_y1),
                        "top_right": (bbox_x2, bbox_y1),
                        "bottom_left": (bbox_x1, bbox_y2),
                        "bottom_right": (bbox_x2, bbox_y2)
                    }
                    
                    # Use handle center positions for detection (rectangular area detection)
                    handle_half_size = handle_size // 2
                    
                    # Check if mouse is in handle's rectangular area
                    def is_in_handle_rect(mx, my, hx, hy):
                        return (hx - handle_half_size <= mx <= hx + handle_half_size and 
                                hy - handle_half_size <= my <= hy + handle_half_size)
                    
                    if is_in_handle_rect(mouse_x, mouse_y, handle_centers["bottom_right"][0], handle_centers["bottom_right"][1]):
                        # Clicked bottom-right resize handle
                        self.drag_mode = "resize"
                        self.resize_handle = "bottom_right"
                        self.handle_click_stats["detected"] += 1
                    elif is_in_handle_rect(mouse_x, mouse_y, handle_centers["top_left"][0], handle_centers["top_left"][1]):
                        # Clicked top-left resize handle
                        self.drag_mode = "resize"
                        self.resize_handle = "top_left"
                        self.handle_click_stats["detected"] += 1
                    elif is_in_handle_rect(mouse_x, mouse_y, handle_centers["top_right"][0], handle_centers["top_right"][1]):
                        # Clicked top-right resize handle
                        self.drag_mode = "resize"
                        self.resize_handle = "top_right"
                        self.handle_click_stats["detected"] += 1
                    elif is_in_handle_rect(mouse_x, mouse_y, handle_centers["bottom_left"][0], handle_centers["bottom_left"][1]):
                        # Clicked bottom-left resize handle
                        self.drag_mode = "resize"
                        self.resize_handle = "bottom_left"
                        self.handle_click_stats["detected"] += 1
                    else:
                        # Clicked inside bounding box, perform move
                        self.drag_mode = "move"
                        self.resize_handle = None
                    
                    self.selected_bbox = i
                    self.dragging = True
                    self.drag_start_pos = pos
                    self.drag_bbox_index = i
                    self.bbox_clicked.emit(i)
                    self.update()  # Redraw
                    bbox_clicked = True
                    break
            
            # Record click position (for zoom center)
            self.last_click_pos = pos
            
            # If no bounding box was clicked, start panning image
            if not bbox_clicked:
                self.panning = True
                self.pan_start_pos = pos
                self.setCursor(Qt.ClosedHandCursor)  # Set hand cursor

# === Main Window ===
class AnnotationToolWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.matched_pairs = load_matched_pairs()
        self.total_frames = len(self.matched_pairs)
        self.current_frame_index = 0
        self.current_annotations = []
        self.is_modified = False  # Track if current frame has been modified
        self.updating_inputs = False  # Suppress textChanged side-effects during UI updates
        self._updating_frame_controls = False  # Suppress frame control recursion
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.timeout.connect(self._autosave_now)
        self._is_autosaving = False
        self._bbox_count_cache = {}  # frame_index -> bbox count (best-effort cache)
        # Persist last position across app restarts
        self._session_state_path = Path(__file__).resolve().parent / ".annotation_tool_state.json"
        self._session_state_timer = QTimer(self)
        self._session_state_timer.setSingleShot(True)
        self._session_state_timer.timeout.connect(self._save_session_state_now)
        
        if self.total_frames == 0:
            QMessageBox.critical(self, "Error", "No matching image/JSON file pairs found!")
            sys.exit(1)
        
        self.init_ui()
        state = self._load_session_state()
        if state is not None:
            frame_index, bbox_index = state
            self.load_frame(frame_index, select_bbox_index=bbox_index)
        else:
            self.load_frame(0)
        
    def init_ui(self):
        """Initialize user interface"""
        self.setWindowTitle("Image Annotation Tool")
        self.setGeometry(100, 100, 2000, 1400)  # Further increase window size
        
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QHBoxLayout(central_widget)
        
        # Create splitter
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # Left image display area
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        # Image display component
        self.image_display = ImageDisplayWidget()
        self.image_display.bbox_clicked.connect(self.on_bbox_clicked)
        self.image_display.bbox_modified.connect(self.on_bbox_modified)
        self.image_display.zoom_changed.connect(self.on_zoom_changed)
        left_layout.addWidget(self.image_display)
        
        # Add stretch space to let image display area occupy more space
        left_layout.addStretch()
        
        # Frame control bar (compact + centered + styled)
        frame_bar = QFrame()
        frame_bar.setObjectName("frameBar")
        frame_bar_layout = QHBoxLayout(frame_bar)
        frame_bar_layout.setContentsMargins(14, 10, 14, 10)
        frame_bar_layout.setSpacing(12)

        self.prev_btn = QPushButton("←")
        self.next_btn = QPushButton("→")
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setMinimum(0)
        self.frame_slider.setMaximum(self.total_frames - 1)
        # Keep the progress bar visually compact (requested)
        self.frame_slider.setFixedWidth(500)

        # 1-based frame index input (numerator) + total (denominator)
        self.frame_prefix_label = QLabel("Frame")
        self.frame_index_input = QSpinBox()
        self.frame_index_input.setMinimum(1)
        self.frame_index_input.setMaximum(self.total_frames)
        self.frame_index_input.setValue(1)
        self.frame_index_input.setFixedWidth(110)
        self.frame_total_label = QLabel(f"/ {self.total_frames}")

        # Sizes
        for btn in (self.prev_btn, self.next_btn):
            btn.setFixedSize(34, 30)
            btn.setFocusPolicy(Qt.NoFocus)
        self.frame_prefix_label.setFixedWidth(55)

        # Center the whole control group in the bar
        frame_bar_layout.addStretch(1)
        frame_bar_layout.addWidget(self.prev_btn)
        frame_bar_layout.addWidget(self.frame_slider)
        frame_bar_layout.addWidget(self.next_btn)
        frame_bar_layout.addSpacing(18)
        frame_bar_layout.addWidget(self.frame_prefix_label)
        frame_bar_layout.addWidget(self.frame_index_input)
        frame_bar_layout.addWidget(self.frame_total_label)
        frame_bar_layout.addStretch(1)

        # Styling (macOS-like, subtle)
        frame_bar.setStyleSheet("""
            QFrame#frameBar {
                background: #F2F2F7;
                border: 1px solid #D1D1D6;
                border-radius: 12px;
            }
            QPushButton {
                background: #FFFFFF;
                border: 1px solid #D1D1D6;
                border-radius: 8px;
                color: #1C1C1E;
                font-size: 16px;
                padding: 0px 10px;
            }
            QPushButton:hover { background: #FFFFFF; border-color: #AFAFB5; }
            QPushButton:pressed { background: #E9E9ED; }
            QSpinBox {
                background: #FFFFFF;
                border: 1px solid #D1D1D6;
                border-radius: 8px;
                padding: 2px 8px;
                min-height: 28px;
            }
            QLabel { color: #1C1C1E; }
            QSlider::groove:horizontal {
                height: 6px;
                background: #D1D1D6;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #0A84FF;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                border: 1px solid #D1D1D6;
                width: 14px;
                margin: -6px 0;
                border-radius: 7px;
            }
        """)

        left_layout.addWidget(frame_bar, alignment=Qt.AlignHCenter)
        
        # Zoom control (hidden display but functionality preserved)
        self.zoom_label = QLabel("Zoom: 100% (Mouse wheel to zoom, Drag to pan, Double-click to reset)")
        # Not added to layout, but keep reference to support zoom functionality
        
        # File information (removed to save space)
        # self.file_info_label = QLabel("File Information")
        # left_layout.addWidget(self.file_info_label)
        
        splitter.addWidget(left_widget)
        
        # Set splitter ratio
        splitter.setSizes([1200, 500])  # Increase right panel width
        
        # Right control panel
        right_widget = QWidget()
        right_widget.setMinimumWidth(500)  # Ensure a wider right panel
        right_layout = QVBoxLayout(right_widget)
        
        # Bounding box list (simplified title)
        bbox_group = QGroupBox("BBox List")
        bbox_layout = QVBoxLayout(bbox_group)
        
        self.bbox_list = QListWidget()
        # Set maximum height to limit BBox List size
        self.bbox_list.setMaximumHeight(200)
        self.bbox_list.currentRowChanged.connect(self.on_bbox_list_selection)
        bbox_layout.addWidget(self.bbox_list)
        
        right_layout.addWidget(bbox_group)
        
        # Edit controls (simplified title and labels)
        edit_group = QGroupBox("Edit")
        edit_layout = QGridLayout(edit_group)
        
        edit_layout.addWidget(QLabel("Class:"), 0, 0)
        self.class_input = QLineEdit()
        self.class_input.returnPressed.connect(self.on_class_enter_pressed)
        edit_layout.addWidget(self.class_input, 0, 1)
        
        # OpenVocab removed

        edit_layout.addWidget(QLabel("Class Detailed:"), 2, 0)
        self.class_detailed_input = QLineEdit()
        self.class_detailed_input.returnPressed.connect(self.on_class_detailed_enter_pressed)
        edit_layout.addWidget(self.class_detailed_input, 2, 1)

        edit_layout.addWidget(QLabel("Detailed Caption:"), 3, 0)
        self.detailed_caption_input = QTextEdit()
        self.detailed_caption_input.setMinimumHeight(120)
        self.detailed_caption_input.setLineWrapMode(QTextEdit.WidgetWidth)
        edit_layout.addWidget(self.detailed_caption_input, 3, 1)
        
        edit_layout.addWidget(QLabel("Top Left X:"), 4, 0)
        self.x1_input = QSpinBox()
        self.x1_input.setMaximum(9999)
        edit_layout.addWidget(self.x1_input, 4, 1)
        
        edit_layout.addWidget(QLabel("Top Left Y:"), 5, 0)
        self.y1_input = QSpinBox()
        self.y1_input.setMaximum(9999)
        edit_layout.addWidget(self.y1_input, 5, 1)
        
        edit_layout.addWidget(QLabel("Bottom Right X:"), 6, 0)
        self.x2_input = QSpinBox()
        self.x2_input.setMaximum(9999)
        edit_layout.addWidget(self.x2_input, 6, 1)
        
        edit_layout.addWidget(QLabel("Bottom Right Y:"), 7, 0)
        self.y2_input = QSpinBox()
        self.y2_input.setMaximum(9999)
        edit_layout.addWidget(self.y2_input, 7, 1)
        
        # Edit buttons - removed rename button
        # button_layout = QHBoxLayout()
        # self.rename_btn = QPushButton("Rename")
        # button_layout.addWidget(self.rename_btn)
        # edit_layout.addLayout(button_layout, 6, 0, 1, 2)
        
        right_layout.addWidget(edit_group)
        
        # Operation buttons (simplified title)
        operation_group = QGroupBox("Actions")
        operation_layout = QVBoxLayout(operation_group)
        
        operation_button_layout = QHBoxLayout()
        self.add_bbox_btn = QPushButton("Add")
        self.delete_bbox_btn = QPushButton("Delete")
        operation_button_layout.addWidget(self.add_bbox_btn)
        operation_button_layout.addWidget(self.delete_bbox_btn)
        operation_layout.addLayout(operation_button_layout)
        
        self.save_btn = QPushButton("Save")
        operation_layout.addWidget(self.save_btn)
        
        right_layout.addWidget(operation_group)
        
        # Status display (simplified)
        self.status_text = QTextEdit()
        self.status_text.setMinimumHeight(100)  # Increase status area height
        self.status_text.setReadOnly(True)
        right_layout.addWidget(QLabel("Status:"))
        right_layout.addWidget(self.status_text)
        
        splitter.addWidget(right_widget)
        
        # Set splitter ratio - increase right panel width
        splitter.setSizes([1200, 800])  # Left ~1200, right ~800
        
        # Connect signals
        self.connect_signals()

        # Global shortcuts: A=prev bbox, D=next bbox (work immediately on launch)
        self._shortcut_prev_bbox = QShortcut(Qt.Key_A, self)
        self._shortcut_prev_bbox.setContext(Qt.ApplicationShortcut)
        self._shortcut_prev_bbox.activated.connect(self.select_prev_bbox)

        self._shortcut_next_bbox = QShortcut(Qt.Key_D, self)
        self._shortcut_next_bbox.setContext(Qt.ApplicationShortcut)
        self._shortcut_next_bbox.activated.connect(self.select_next_bbox)

        # Delete bbox shortcut: Delete / Backspace
        self._shortcut_delete_bbox = QShortcut(Qt.Key_Delete, self)
        self._shortcut_delete_bbox.setContext(Qt.ApplicationShortcut)
        self._shortcut_delete_bbox.activated.connect(self.delete_bbox_shortcut)

        self._shortcut_backspace_delete_bbox = QShortcut(Qt.Key_Backspace, self)
        self._shortcut_backspace_delete_bbox.setContext(Qt.ApplicationShortcut)
        self._shortcut_backspace_delete_bbox.activated.connect(self.delete_bbox_shortcut)
        
    def connect_signals(self):
        """Connect signals and slots"""
        self.prev_btn.clicked.connect(self.previous_frame)
        self.next_btn.clicked.connect(self.next_frame)
        self.frame_slider.valueChanged.connect(self.on_frame_slider_changed)
        self.frame_index_input.valueChanged.connect(self.on_frame_index_input_changed)
        
        # self.rename_btn.clicked.connect(self.rename_bbox)  # Removed rename button
        self.add_bbox_btn.clicked.connect(self.add_bbox)
        self.delete_bbox_btn.clicked.connect(self.delete_bbox)
        self.save_btn.clicked.connect(self.save_annotations)
        
        # self.export_json_btn.clicked.connect(self.export_json)  # Removed export functionality
        
        # Connect coordinate input box real-time update signals
        self.x1_input.valueChanged.connect(self.on_coord_changed)
        self.y1_input.valueChanged.connect(self.on_coord_changed)
        self.x2_input.valueChanged.connect(self.on_coord_changed)
        self.y2_input.valueChanged.connect(self.on_coord_changed)
        # Track text edits to prompt unsaved changes
        self.class_input.textChanged.connect(self.on_text_modified)
        self.class_detailed_input.textChanged.connect(self.on_text_modified)
        self.detailed_caption_input.textChanged.connect(self.on_text_modified)
        
        # Zoom control signals already implemented through mouse wheel
        
    def load_frame(self, frame_index: int, select_bbox_index: Optional[int] = None):
        """Load specified frame"""
        if 0 <= frame_index < self.total_frames:
            # Auto-save before switching frames (no prompt)
            self.flush_autosave()
            
            self.current_frame_index = frame_index
            
            # Load image
            img_path, json_path = self.matched_pairs[frame_index]
            self.image_display.set_image(img_path)
            
            # Load annotations
            try:
                with open(json_path, 'r') as f:
                    self.current_annotations = json.load(f)
            except Exception as e:
                self.current_annotations = []
                self.log_status(f"⚠️ Error loading annotations: {e}")
            # Update bbox count cache
            try:
                self._bbox_count_cache[frame_index] = len(self.current_annotations) if isinstance(self.current_annotations, list) else 0
            except Exception:
                self._bbox_count_cache[frame_index] = 0
            
            # Reset modified flag for new frame
            self.is_modified = False
            
            # Update interface
            self.update_ui()

            # Select bbox on load:
            # - default: first bbox (0) if exists
            # - caller can override with select_bbox_index (supports negative for "from end")
            if len(self.current_annotations) > 0:
                idx = 0 if select_bbox_index is None else select_bbox_index
                if idx < 0:
                    idx = len(self.current_annotations) - 1
                if idx >= len(self.current_annotations):
                    idx = len(self.current_annotations) - 1
                self.bbox_list.setCurrentRow(idx)
                self.image_display.set_selected_bbox(idx)
                self.update_inputs()
            else:
                self.clear_inputs()
            
            self.log_status(f"✅ Loaded frame {frame_index + 1}: {img_path.name}")
            self.schedule_session_state_save()
            
    def update_ui(self):
        """Update user interface"""
        # Update frame information (avoid recursion)
        self._updating_frame_controls = True
        try:
            self.frame_slider.setValue(self.current_frame_index)
            self.frame_index_input.setValue(self.current_frame_index + 1)
        finally:
            self._updating_frame_controls = False
        
        
        # Update bounding box list
        self.update_bbox_list()
        
        # Update image display
        self.image_display.set_annotations(self.current_annotations)
        # Selection is controlled by caller (e.g., auto-select first bbox on load)
        
    def update_bbox_list(self):
        """Update bounding box list"""
        self.bbox_list.clear()
        for i, ann in enumerate(self.current_annotations):
            class_detailed = ann.get("class_detailed", "")
            detailed_caption = ann.get("detailed_caption", "")
            parts = [f"{i}:", ann.get('class', '')]
            if class_detailed:
                parts.append(f"<{class_detailed}>")
            if detailed_caption:
                short_cap = detailed_caption[:40] + ("…" if len(detailed_caption) > 40 else "")
                parts.append(f"cap={short_cap}")
            parts.append(str(ann.get('box', '')))
            self.bbox_list.addItem(" ".join(parts))

    def _refresh_bbox_list_preserve_selection(self, prefer_row: Optional[int] = None):
        """Refresh bbox list text while keeping selection and not triggering input resets."""
        row = self.bbox_list.currentRow() if prefer_row is None else int(prefer_row)
        if len(self.current_annotations) == 0:
            row = -1
        elif row >= len(self.current_annotations):
            row = len(self.current_annotations) - 1

        self.bbox_list.blockSignals(True)
        self.bbox_list.setUpdatesEnabled(False)
        try:
            self.update_bbox_list()
            if row >= 0:
                self.bbox_list.setCurrentRow(row)
        finally:
            self.bbox_list.setUpdatesEnabled(True)
            self.bbox_list.blockSignals(False)
            
    def on_frame_slider_changed(self, value):
        """Frame slider change event"""
        if self._updating_frame_controls:
            return
        if value != self.current_frame_index:
            self.load_frame(value)

    def on_frame_index_input_changed(self, value: int):
        """Frame index input changed (1-based): jump to that frame."""
        if self._updating_frame_controls:
            return
        target = int(value) - 1
        if 0 <= target < self.total_frames and target != self.current_frame_index:
            self.load_frame(target)
            
    def previous_frame(self):
        """Previous frame"""
        if self.current_frame_index > 0:
            self.load_frame(self.current_frame_index - 1)
            
    def next_frame(self):
        """Next frame"""
        if self.current_frame_index < self.total_frames - 1:
            self.load_frame(self.current_frame_index + 1)
            
    def on_bbox_clicked(self, bbox_index):
        """Bounding box click event"""
        self.bbox_list.setCurrentRow(bbox_index)
        self.image_display.set_selected_bbox(bbox_index)
        self.update_inputs()
        self.schedule_session_state_save()

    def on_bbox_modified(self, bbox_index):
        """Bounding box data changed from drag/resize on canvas."""
        if not (0 <= bbox_index < len(self.current_annotations)):
            return
        self.is_modified = True
        # Refresh list text to reflect updated coords
        self._refresh_bbox_list_preserve_selection()
        self.schedule_autosave()
        
    def on_zoom_changed(self, scale_factor):
        """Zoom change event"""
        self.zoom_label.setText(f"Zoom: {int(scale_factor * 100)}%")
        
    def on_coord_changed(self):
        """Coordinate input box change event - real-time update bounding box"""
        current_row = self.bbox_list.currentRow()
        if current_row < 0 or current_row >= len(self.current_annotations):
            return
            
        # Get current input values
        x1 = self.x1_input.value()
        y1 = self.y1_input.value()
        x2 = self.x2_input.value()
        y2 = self.y2_input.value()
        
        # Validate coordinate validity
        if x1 >= x2 or y1 >= y2:
            return  # Invalid coordinates, don't update
            
        # Update current bounding box coordinates
        self.current_annotations[current_row]['box'] = [int(x1), int(y1), int(x2), int(y2)]
        self.is_modified = True  # Mark as modified
        
        # Real-time update image display
        self.image_display.set_annotations(self.current_annotations)
        
        # Update list display
        self._refresh_bbox_list_preserve_selection(prefer_row=current_row)
        self.schedule_autosave()
        

        
    def on_bbox_list_selection(self, row):
        """Bounding box list selection event"""
        if 0 <= row < len(self.current_annotations):
            self.image_display.set_selected_bbox(row)
            self.update_inputs()
            self.schedule_session_state_save()
            
    def update_inputs(self):
        """Update input boxes"""
        current_row = self.bbox_list.currentRow()
        if 0 <= current_row < len(self.current_annotations):
            bbox = self.current_annotations[current_row]
            self.updating_inputs = True
            self.class_input.setText(bbox['class'])
            self.class_detailed_input.setText(bbox.get('class_detailed', ''))
            self.detailed_caption_input.setPlainText(bbox.get('detailed_caption', ''))
            
            # Temporarily disconnect signal connections to avoid triggering real-time updates
            self.x1_input.valueChanged.disconnect()
            self.y1_input.valueChanged.disconnect()
            self.x2_input.valueChanged.disconnect()
            self.y2_input.valueChanged.disconnect()
            
            # Convert float to integer
            self.x1_input.setValue(int(bbox['box'][0]))
            self.y1_input.setValue(int(bbox['box'][1]))
            self.x2_input.setValue(int(bbox['box'][2]))
            self.y2_input.setValue(int(bbox['box'][3]))
            
            # Reconnect signals
            self.x1_input.valueChanged.connect(self.on_coord_changed)
            self.y1_input.valueChanged.connect(self.on_coord_changed)
            self.x2_input.valueChanged.connect(self.on_coord_changed)
            self.y2_input.valueChanged.connect(self.on_coord_changed)
            self.updating_inputs = False
        else:
            self.clear_inputs()
            
    def clear_inputs(self):
        """Clear input boxes"""
        self.updating_inputs = True
        self.class_input.clear()
        self.class_detailed_input.clear()
        self.detailed_caption_input.clear()
        self.x1_input.setValue(0)
        self.y1_input.setValue(0)
        self.x2_input.setValue(0)
        self.y2_input.setValue(0)
        self.updating_inputs = False
        

    def on_class_enter_pressed(self):
        """Handle Enter key press in class input"""
        current_row = self.bbox_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "Warning", "Please select a bounding box first")
            return
            
        new_class = self.class_input.text().strip()
        if not new_class:
            QMessageBox.warning(self, "Warning", "Please enter a class name")
            return
            
        self.current_annotations[current_row]['class'] = new_class
        self.is_modified = True  # Mark as modified
        
        # Update image display and list
        self.image_display.set_annotations(self.current_annotations)
        self._refresh_bbox_list_preserve_selection(prefer_row=current_row)
        self.image_display.set_selected_bbox(current_row)
        
        self.log_status(f"✅ Updated class to: {new_class}")
        self.schedule_autosave()
        
    # OpenVocab handler removed

    def on_class_detailed_enter_pressed(self):
        """Handle Enter key press in class_detailed input"""
        current_row = self.bbox_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "Warning", "Please select a bounding box first")
            return
        value = self.class_detailed_input.text().strip()
        if value:
            self.current_annotations[current_row]['class_detailed'] = value
        elif 'class_detailed' in self.current_annotations[current_row]:
            del self.current_annotations[current_row]['class_detailed']
        self.is_modified = True
        self._refresh_bbox_list_preserve_selection(prefer_row=current_row)
        self.image_display.set_annotations(self.current_annotations)
        self.image_display.set_selected_bbox(current_row)
        if value:
            self.log_status(f"✅ Updated class_detailed to: {value}")
        else:
            self.log_status("✅ Removed class_detailed")
        self.schedule_autosave()

    def add_bbox(self):
        """Add bounding box"""
        # Get image dimensions
        img_path, _ = self.matched_pairs[self.current_frame_index]
        with Image.open(img_path) as img:
            width, height = img.size
            
        # Add bounding box at image center
        center_x, center_y = width // 2, height // 2
        size = 100
        
        new_bbox = {
            "class": "new_object",
            "box": [int(center_x - size//2), int(center_y - size//2), 
                   int(center_x + size//2), int(center_y + size//2)],
            "score": 1.0
        }
        
        self.current_annotations.append(new_bbox)
        self.is_modified = True  # Mark as modified
        # Update cache immediately (count changed)
        self._bbox_count_cache[self.current_frame_index] = len(self.current_annotations)
        self.update_ui()
        self.log_status("✅ Added new bounding box")
        self.schedule_autosave()
        
    def delete_bbox(self):
        """Delete bounding box"""
        current_row = self.bbox_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "Warning", "Please select a bounding box first")
            return
        
        deleted_class = self.current_annotations[current_row].get('class', '')
        del self.current_annotations[current_row]
        self.is_modified = True  # Mark as modified
        # Update cache immediately (count changed)
        self._bbox_count_cache[self.current_frame_index] = len(self.current_annotations)
        self.update_ui()
        self.clear_inputs()
        self.log_status(f"✅ Deleted bounding box {current_row}: {deleted_class}")
        # Auto-save deletion immediately (no prompt)
        self.flush_autosave()
            
    def save_annotations(self):
        """Save annotations"""
        # Sync current UI edits into model before saving
        current_row = self.bbox_list.currentRow()
        if 0 <= current_row < len(self.current_annotations):
            self.current_annotations[current_row]['class'] = self.class_input.text().strip()
            cd = self.class_detailed_input.text().strip()
            dc = self.detailed_caption_input.toPlainText().strip()
            if cd:
                self.current_annotations[current_row]['class_detailed'] = cd
            elif 'class_detailed' in self.current_annotations[current_row]:
                del self.current_annotations[current_row]['class_detailed']
            if dc:
                self.current_annotations[current_row]['detailed_caption'] = dc
            elif 'detailed_caption' in self.current_annotations[current_row]:
                del self.current_annotations[current_row]['detailed_caption']

        # Strip any OpenVocab keys from annotations before saving
        for ann in self.current_annotations:
            if isinstance(ann, dict) and 'openvocab' in ann:
                try:
                    del ann['openvocab']
                except Exception:
                    pass
        _, json_path = self.matched_pairs[self.current_frame_index]
        try:
            self._is_autosaving = True
            with open(json_path, 'w') as f:
                json.dump(self.current_annotations, f, indent=2)
            self.is_modified = False  # Reset modified flag after successful save
            # Keep cache in sync
            self._bbox_count_cache[self.current_frame_index] = len(self.current_annotations) if isinstance(self.current_annotations, list) else 0
            # Refresh list text without triggering selection -> input resets (prevents cursor jump)
            self._refresh_bbox_list_preserve_selection()
            self.log_status(f"✅ Saved to: {json_path.name}")
        except Exception as e:
            self.log_status(f"❌ Save failed: {e}")
        finally:
            self._is_autosaving = False
            

                
    def log_status(self, message):
        """Log status information"""
        self.status_text.append(f"[{QApplication.instance().applicationName()}] {message}")
        self.status_text.ensureCursorVisible()
        
    def on_text_modified(self, *_args):
        """Mark as modified when text edits occur (for unsaved-change prompts)."""
        if self.updating_inputs or self._is_autosaving:
            return
        self.is_modified = True
        self.schedule_autosave()

    def schedule_autosave(self, delay_ms: int = 250):
        """Debounced autosave for any annotation change."""
        if not self.is_modified:
            return
        # Restart debounce timer
        self._autosave_timer.start(max(0, int(delay_ms)))

    def flush_autosave(self):
        """Force save immediately if there are pending changes."""
        if self._autosave_timer.isActive():
            self._autosave_timer.stop()
        if self.is_modified:
            self._autosave_now()

    def schedule_session_state_save(self, delay_ms: int = 300):
        """Debounced save of last frame/bbox position for next launch."""
        self._session_state_timer.start(max(0, int(delay_ms)))

    def flush_session_state_save(self):
        """Force save session state immediately."""
        if self._session_state_timer.isActive():
            self._session_state_timer.stop()
        self._save_session_state_now()

    def _save_session_state_now(self):
        """Internal: write last frame/bbox position to disk."""
        try:
            bbox_row = self.bbox_list.currentRow()
            bbox_index = int(bbox_row) if bbox_row >= 0 else None
            payload = {
                "frame_index": int(self.current_frame_index),
                "bbox_index": bbox_index,
            }
            with open(self._session_state_path, "w") as f:
                json.dump(payload, f, indent=2)
        except Exception:
            # Best-effort persistence; never block the UI on failures
            pass

    def _load_session_state(self) -> Optional[tuple]:
        """Return (frame_index, bbox_index) if saved, else None."""
        try:
            if not self._session_state_path.exists():
                return None
            with open(self._session_state_path, "r") as f:
                data = json.load(f)
            frame_index = int(data.get("frame_index", 0))
            bbox_index = data.get("bbox_index", None)
            bbox_index = None if bbox_index is None else int(bbox_index)
            if frame_index < 0 or frame_index >= self.total_frames:
                return None
            return (frame_index, bbox_index)
        except Exception:
            return None

    def closeEvent(self, event):
        """Persist edits and last position on app close."""
        try:
            self.flush_autosave()
            self.flush_session_state_save()
        finally:
            event.accept()

    def _autosave_now(self):
        """Internal: perform autosave without user interaction."""
        if not self.is_modified:
            return
        self.save_annotations()

    def delete_bbox_shortcut(self):
        """Delete currently selected bbox via shortcut."""
        # Avoid hijacking Backspace/Delete while user edits text
        fw = QApplication.focusWidget()
        if isinstance(fw, (QLineEdit, QTextEdit)):
            return
        self.delete_bbox()

    def _get_frame_bbox_count(self, frame_index: int) -> int:
        """Best-effort: return bbox count for a frame without switching UI."""
        if frame_index in self._bbox_count_cache:
            return int(self._bbox_count_cache.get(frame_index, 0) or 0)
        try:
            _, json_path = self.matched_pairs[frame_index]
            with open(json_path, 'r') as f:
                data = json.load(f)
            count = len(data) if isinstance(data, list) else 0
            self._bbox_count_cache[frame_index] = count
            return count
        except Exception:
            self._bbox_count_cache[frame_index] = 0
            return 0

    def _find_next_frame_with_bbox(self, start_index: int) -> Optional[int]:
        """Return the next frame index > start_index that has at least 1 bbox."""
        for i in range(start_index + 1, self.total_frames):
            if self._get_frame_bbox_count(i) > 0:
                return i
        return None

    def _find_prev_frame_with_bbox(self, start_index: int) -> Optional[int]:
        """Return the previous frame index < start_index that has at least 1 bbox."""
        for i in range(start_index - 1, -1, -1):
            if self._get_frame_bbox_count(i) > 0:
                return i
        return None

    def select_prev_bbox(self):
        """Select previous bounding box (A)."""
        n = len(self.current_annotations)
        cur = self.bbox_list.currentRow()
        if n > 0 and cur > 0:
            self.bbox_list.setCurrentRow(cur - 1)
            return

        # At first bbox (or no selection) -> jump to previous frame's last bbox
        prev_frame = self._find_prev_frame_with_bbox(self.current_frame_index)
        if prev_frame is None:
            # No previous frame with bbox; if current has bboxes, ensure selection
            if n > 0:
                self.bbox_list.setCurrentRow(0)
            return
        self.load_frame(prev_frame, select_bbox_index=-1)

    def select_next_bbox(self):
        """Select next bounding box (D)."""
        n = len(self.current_annotations)
        cur = self.bbox_list.currentRow()
        if n > 0 and 0 <= cur < n - 1:
            self.bbox_list.setCurrentRow(cur + 1)
            return

        # At last bbox (or no selection / empty) -> jump to next frame's first bbox
        next_frame = self._find_next_frame_with_bbox(self.current_frame_index)
        if next_frame is None:
            # No next frame with bbox; if current has bboxes, ensure selection on last
            if n > 0:
                self.bbox_list.setCurrentRow(max(0, n - 1))
            return
        self.load_frame(next_frame, select_bbox_index=0)

    # NOTE: A/D shortcuts are implemented via QShortcut with ApplicationShortcut


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PyQt Annotation Tool")

    window = AnnotationToolWindow()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
