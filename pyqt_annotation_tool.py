import sys
import os
import json
from pathlib import Path
from PIL import Image, ImageDraw
import numpy as np
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QSlider, QListWidget,
                             QLineEdit, QSpinBox, QMessageBox, QFileDialog, QGroupBox,
                             QGridLayout, QSplitter, QFrame, QTextEdit, QComboBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QFont, QImage
import cv2

# === Configuration Parameters ===
image_dir = Path("sample_frames")
json_dir = Path("sample_jsons")
CACHE_WINDOW = 10

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
                        print(f"Coordinate conversion error: {e}")
                        new_box = list(old_box)
                
                # Ensure bounding box is valid and within image bounds
                widget_size = self.size()
                image_size = self.image.size()
                
                print(f"New bounding box: {new_box}")
                print(f"Image size: {image_size.width()} x {image_size.height()}")
                
                # Check if bounding box is valid
                is_valid_size = len(new_box) == 4
                is_valid_coords = new_box[0] < new_box[2] and new_box[1] < new_box[3]
                is_in_bounds = (new_box[0] >= 0 and new_box[1] >= 0 and 
                               new_box[2] <= image_size.width() and new_box[3] <= image_size.height())
                
                print(f"BBox validation: size_valid={is_valid_size}, coords_valid={is_valid_coords}, in_bounds={is_in_bounds}")
                
                if is_valid_size and is_valid_coords and is_in_bounds:
                    try:
                        bbox["box"] = new_box
                        self.update()
                        
                        # Send signal to notify main window to update input fields
                        self.bbox_clicked.emit(self.drag_bbox_index)
                        print(f"✅ Bounding box updated successfully")
                    except Exception as e:
                        print(f"❌ Bounding box update failed: {e}")
                else:
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
            
            # If it's the selected bounding box, draw resize handles
            if i == self.selected_bbox:
                handle_size = 16  # Increase handle size to match detection area
                # Draw resize handles at four corners
                painter.setPen(QPen(QColor(255, 255, 0), 2))
                painter.setBrush(QColor(255, 255, 0))
                
                # Calculate handle positions
                handle_positions = {
                    "top_left": (int(x1 - handle_size//2), int(y1 - handle_size//2)),
                    "top_right": (int(x2 - handle_size//2), int(y1 - handle_size//2)),
                    "bottom_left": (int(x1 - handle_size//2), int(y2 - handle_size//2)),
                    "bottom_right": (int(x2 - handle_size//2), int(y2 - handle_size//2))
                }
                
                # Draw handles
                for handle_name, (hx, hy) in handle_positions.items():
                    painter.drawRect(hx, hy, handle_size, handle_size)
            
            # Draw label
            font = QFont("Arial", 10)
            painter.setFont(font)
            painter.setPen(QPen(QColor(255, 255, 0), 1))
            
            # Label background
            text_rect = painter.fontMetrics().boundingRect(f"{label} {i}")
            painter.fillRect(int(x1), int(y1 - text_rect.height() - 5), 
                           text_rect.width() + 10, text_rect.height() + 5, 
                           QColor(0, 0, 0, 180))
            
            # Draw text
            painter.drawText(int(x1 + 5), int(y1 - 5), f"{label} {i}")
    
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
        
        if self.total_frames == 0:
            QMessageBox.critical(self, "Error", "No matching image/JSON file pairs found!")
            sys.exit(1)
        
        self.init_ui()
        self.load_frame(0)
        
    def init_ui(self):
        """Initialize user interface"""
        self.setWindowTitle("🎯 PyQt Image Annotation Tool")
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
        self.image_display.zoom_changed.connect(self.on_zoom_changed)
        left_layout.addWidget(self.image_display)
        
        # Add stretch space to let image display area occupy more space
        left_layout.addStretch()
        
        # Simplified frame control (more compact, placed at bottom)
        frame_control_layout = QHBoxLayout()
        
        self.prev_btn = QPushButton("⬅️")
        self.next_btn = QPushButton("➡️")
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setMinimum(0)
        self.frame_slider.setMaximum(self.total_frames - 1)
        self.frame_label = QLabel(f"Frame 1/{self.total_frames}")
        
        # Set minimum size for buttons and labels
        self.prev_btn.setMaximumWidth(40)
        self.next_btn.setMaximumWidth(40)
        self.frame_label.setMaximumWidth(80)
        
        frame_control_layout.addWidget(self.prev_btn)
        frame_control_layout.addWidget(self.frame_slider)
        frame_control_layout.addWidget(self.next_btn)
        frame_control_layout.addWidget(self.frame_label)
        
        left_layout.addLayout(frame_control_layout)
        
        # Zoom control (hidden display but functionality preserved)
        self.zoom_label = QLabel("Zoom: 100% (Mouse wheel to zoom, Drag to pan, Double-click to reset)")
        # Not added to layout, but keep reference to support zoom functionality
        
        # File information (removed to save space)
        # self.file_info_label = QLabel("File Information")
        # left_layout.addWidget(self.file_info_label)
        
        splitter.addWidget(left_widget)
        
        # Set splitter ratio to make left image area larger
        splitter.setSizes([1200, 300])  # Left 1200 pixels, right 300 pixels
        
        # Right control panel
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # Bounding box list (simplified title)
        bbox_group = QGroupBox("BBox List")
        bbox_layout = QVBoxLayout(bbox_group)
        
        self.bbox_list = QListWidget()
        # Remove height limit to let list fill entire GroupBox
        self.bbox_list.currentRowChanged.connect(self.on_bbox_list_selection)
        bbox_layout.addWidget(self.bbox_list)
        
        right_layout.addWidget(bbox_group)
        
        # Edit controls (simplified title and labels)
        edit_group = QGroupBox("Edit")
        edit_layout = QGridLayout(edit_group)
        
        edit_layout.addWidget(QLabel("Class:"), 0, 0)
        self.class_input = QLineEdit()
        edit_layout.addWidget(self.class_input, 0, 1)
        
        edit_layout.addWidget(QLabel("X1:"), 1, 0)
        self.x1_input = QSpinBox()
        self.x1_input.setMaximum(9999)
        edit_layout.addWidget(self.x1_input, 1, 1)
        
        edit_layout.addWidget(QLabel("Y1:"), 2, 0)
        self.y1_input = QSpinBox()
        self.y1_input.setMaximum(9999)
        edit_layout.addWidget(self.y1_input, 2, 1)
        
        edit_layout.addWidget(QLabel("X2:"), 3, 0)
        self.x2_input = QSpinBox()
        self.x2_input.setMaximum(9999)
        edit_layout.addWidget(self.x2_input, 3, 1)
        
        edit_layout.addWidget(QLabel("Y2:"), 4, 0)
        self.y2_input = QSpinBox()
        self.y2_input.setMaximum(9999)
        edit_layout.addWidget(self.y2_input, 4, 1)
        
        # Edit buttons
        button_layout = QHBoxLayout()
        self.rename_btn = QPushButton("Rename")
        button_layout.addWidget(self.rename_btn)
        edit_layout.addLayout(button_layout, 5, 0, 1, 2)
        
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
        
        # Export functionality (simplified title)
        export_group = QGroupBox("Export")
        export_layout = QVBoxLayout(export_group)
        
        self.export_json_btn = QPushButton("Export JSON")
        export_layout.addWidget(self.export_json_btn)
        
        # Export options
        self.export_format_combo = QComboBox()
        self.export_format_combo.addItems(["Current Frame", "All Frames"])
        export_layout.addWidget(QLabel("Range:"))
        export_layout.addWidget(self.export_format_combo)
        
        right_layout.addWidget(export_group)
        
        # Status display (simplified)
        self.status_text = QTextEdit()
        self.status_text.setMaximumHeight(50)  # Further reduce status area height
        self.status_text.setReadOnly(True)
        right_layout.addWidget(QLabel("Status:"))
        right_layout.addWidget(self.status_text)
        
        splitter.addWidget(right_widget)
        
        # Set splitter ratio - make left image area larger
        splitter.setSizes([1500, 250])  # Left 1500 pixels, right 250 pixels
        
        # Connect signals
        self.connect_signals()
        
    def connect_signals(self):
        """Connect signals and slots"""
        self.prev_btn.clicked.connect(self.previous_frame)
        self.next_btn.clicked.connect(self.next_frame)
        self.frame_slider.valueChanged.connect(self.on_frame_slider_changed)
        
        self.rename_btn.clicked.connect(self.rename_bbox)
        self.add_bbox_btn.clicked.connect(self.add_bbox)
        self.delete_bbox_btn.clicked.connect(self.delete_bbox)
        self.save_btn.clicked.connect(self.save_annotations)
        
        self.export_json_btn.clicked.connect(self.export_json)
        
        # Connect coordinate input box real-time update signals
        self.x1_input.valueChanged.connect(self.on_coord_changed)
        self.y1_input.valueChanged.connect(self.on_coord_changed)
        self.x2_input.valueChanged.connect(self.on_coord_changed)
        self.y2_input.valueChanged.connect(self.on_coord_changed)
        
        # Zoom control signals already implemented through mouse wheel
        
    def load_frame(self, frame_index):
        """Load specified frame"""
        if 0 <= frame_index < self.total_frames:
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
            
            # Update interface
            self.update_ui()
            self.log_status(f"✅ Loaded frame {frame_index + 1}: {img_path.name}")
            
    def update_ui(self):
        """Update user interface"""
        # Update frame information
        self.frame_label.setText(f"Frame {self.current_frame_index + 1}/{self.total_frames}")
        self.frame_slider.setValue(self.current_frame_index)
        
        # Update file information (display removed)
        # img_path, json_path = self.matched_pairs[self.current_frame_index]
        # self.file_info_label.setText(f"Image: {img_path.name}\nJSON: {json_path.name}")
        
        # Update bounding box list
        self.update_bbox_list()
        
        # Update image display
        self.image_display.set_annotations(self.current_annotations)
        
        # Ensure no bounding box is selected (initial state)
        self.image_display.set_selected_bbox(-1)
        
    def update_bbox_list(self):
        """Update bounding box list"""
        self.bbox_list.clear()
        for i, ann in enumerate(self.current_annotations):
            self.bbox_list.addItem(f"{i}: {ann['class']} {ann['box']}")
            
    def on_frame_slider_changed(self, value):
        """Frame slider change event"""
        if value != self.current_frame_index:
            self.load_frame(value)
            
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
        
        # Real-time update image display
        self.image_display.set_annotations(self.current_annotations)
        
        # Update list display
        self.update_bbox_list()
        
        # Maintain current selection
        self.bbox_list.setCurrentRow(current_row)
        

        
    def on_bbox_list_selection(self, row):
        """Bounding box list selection event"""
        if 0 <= row < len(self.current_annotations):
            self.image_display.set_selected_bbox(row)
            self.update_inputs()
            
    def update_inputs(self):
        """Update input boxes"""
        current_row = self.bbox_list.currentRow()
        if 0 <= current_row < len(self.current_annotations):
            bbox = self.current_annotations[current_row]
            self.class_input.setText(bbox['class'])
            
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
        else:
            self.clear_inputs()
            
    def clear_inputs(self):
        """Clear input boxes"""
        self.class_input.clear()
        self.x1_input.setValue(0)
        self.y1_input.setValue(0)
        self.x2_input.setValue(0)
        self.y2_input.setValue(0)
        

    def rename_bbox(self):
        """Rename bounding box"""
        current_row = self.bbox_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "Warning", "Please select a bounding box first")
            return
            
        new_class = self.class_input.text().strip()
        if not new_class:
            QMessageBox.warning(self, "Warning", "Please enter a class name")
            return
            
        self.current_annotations[current_row]['class'] = new_class
        
        # Only update image display and list, don't clear input boxes
        self.image_display.set_annotations(self.current_annotations)
        self.update_bbox_list()
        
        self.log_status(f"✅ Renamed bounding box {current_row} to: {new_class}")
        
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
        self.update_ui()
        self.log_status("✅ Added new bounding box")
        
    def delete_bbox(self):
        """Delete bounding box"""
        current_row = self.bbox_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "Warning", "Please select a bounding box first")
            return
            
        reply = QMessageBox.question(self, "Confirm Delete", 
                                   "Are you sure you want to delete this bounding box?",
                                   QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            deleted_class = self.current_annotations[current_row]['class']
            del self.current_annotations[current_row]
            self.update_ui()
            self.clear_inputs()
            self.log_status(f"✅ Deleted bounding box {current_row}: {deleted_class}")
            
    def save_annotations(self):
        """Save annotations"""
        _, json_path = self.matched_pairs[self.current_frame_index]
        try:
            with open(json_path, 'w') as f:
                json.dump(self.current_annotations, f, indent=2)
            self.log_status(f"✅ Saved to: {json_path.name}")
        except Exception as e:
            self.log_status(f"❌ Save failed: {e}")
            
    def export_json(self):
        """Export JSON format"""
        export_range = self.export_format_combo.currentText()
        
        if export_range == "Current Frame":
            data_to_export = [{
                "frame": self.current_frame_index,
                "image": self.matched_pairs[self.current_frame_index][0].name,
                "annotations": self.current_annotations
            }]
        else:  # All Frames
            data_to_export = []
            for i, (img_path, json_path) in enumerate(self.matched_pairs):
                try:
                    with open(json_path, 'r') as f:
                        annotations = json.load(f)
                    data_to_export.append({
                        "frame": i,
                        "image": img_path.name,
                        "annotations": annotations
                    })
                except Exception as e:
                    self.log_status(f"⚠️ Failed to load frame {i} annotations: {e}")
        
        # Choose save path
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export JSON", "annotations_export.json", "JSON Files (*.json)")
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data_to_export, f, indent=2, ensure_ascii=False)
                self.log_status(f"✅ Exported to: {file_path}")
            except Exception as e:
                self.log_status(f"❌ Export failed: {e}")
                
    def log_status(self, message):
        """Log status information"""
        self.status_text.append(f"[{QApplication.instance().applicationName()}] {message}")
        self.status_text.ensureCursorVisible()
        


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PyQt Annotation Tool")
    
    # Check dependencies
    try:
        import cv2
    except ImportError:
        QMessageBox.warning(None, "Missing Dependency", 
                          "Please install OpenCV: pip install opencv-python")
        return
    
    window = AnnotationToolWindow()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
