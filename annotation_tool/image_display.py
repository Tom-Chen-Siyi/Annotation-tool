from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QWidget

from .config import DEBUG


class ImageDisplayWidget(QWidget):
    bbox_clicked = pyqtSignal(int)  # selected bbox index
    bbox_modified = pyqtSignal(int)  # bbox data changed (drag/resize)

    def __init__(self):
        super().__init__()
        self.image = None
        self.annotations = []
        self.selected_bbox = -1
        self.scale_factor = 1.0
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
        self.setMouseTracking(True)
        self.setMinimumSize(1200, 800)

    def set_image(self, image_path):
        self.image = QPixmap(str(image_path))
        self.update()

    def set_annotations(self, annotations):
        self.annotations = annotations
        self.update()

    def set_selected_bbox(self, index):
        self.selected_bbox = index
        self.update()

    def widget_to_image_coords(self, pos):
        if not self.image:
            return 0, 0

        widget_size = self.size()
        image_size = self.image.size()

        scale_x = widget_size.width() / image_size.width()
        scale_y = widget_size.height() / image_size.height()
        auto_scale = min(scale_x, scale_y, 1.0)

        if self.scale_factor == 1.0:
            self.scale_factor = auto_scale

        scale_factor = self.scale_factor
        scaled_width = int(image_size.width() * scale_factor)
        scaled_height = int(image_size.height() * scale_factor)
        x_offset = (widget_size.width() - scaled_width) // 2 + self.zoom_offset_x
        y_offset = (widget_size.height() - scaled_height) // 2 + self.zoom_offset_y

        image_x = (pos.x() - x_offset) / scale_factor
        image_y = (pos.y() - y_offset) / scale_factor
        return image_x, image_y

    def mouseMoveEvent(self, event):
        # Drag bbox
        if self.dragging and 0 <= self.drag_bbox_index < len(self.annotations):
            current_pos = event.pos()
            if self.drag_start_pos:
                dx = current_pos.x() - self.drag_start_pos.x()
                dy = current_pos.y() - self.drag_start_pos.y()

                image_dx = dx / self.scale_factor
                image_dy = dy / self.scale_factor

                bbox = self.annotations[self.drag_bbox_index]
                old_box = bbox["box"]

                if self.drag_mode == "move":
                    new_box = [
                        int(float(old_box[0]) + image_dx),
                        int(float(old_box[1]) + image_dy),
                        int(float(old_box[2]) + image_dx),
                        int(float(old_box[3]) + image_dy),
                    ]
                else:
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
                        if DEBUG:
                            print(f"Coordinate conversion error: {e}")
                        new_box = list(old_box)

                image_size = self.image.size()

                if DEBUG:
                    print(f"New bounding box: {new_box}")
                    print(f"Image size: {image_size.width()} x {image_size.height()}")

                is_valid_size = len(new_box) == 4
                is_valid_coords = new_box[0] < new_box[2] and new_box[1] < new_box[3]
                is_in_bounds = (
                    new_box[0] >= 0
                    and new_box[1] >= 0
                    and new_box[2] <= image_size.width()
                    and new_box[3] <= image_size.height()
                )

                if DEBUG:
                    print(
                        f"BBox validation: size_valid={is_valid_size}, coords_valid={is_valid_coords}, in_bounds={is_in_bounds}"
                    )

                if is_valid_size and is_valid_coords and is_in_bounds:
                    try:
                        bbox["box"] = new_box
                        self.update()
                        self.bbox_clicked.emit(self.drag_bbox_index)
                        self.bbox_modified.emit(self.drag_bbox_index)
                        if DEBUG:
                            print("✅ Bounding box updated successfully")
                    except Exception as e:
                        if DEBUG:
                            print(f"❌ Bounding box update failed: {e}")
                else:
                    if DEBUG:
                        print(f"❌ Invalid bounding box: size={len(new_box)}, coords={new_box}")
                        if not is_valid_coords:
                            print(
                                f"   Coordinate issue: x1({new_box[0]}) >= x2({new_box[2]}) or y1({new_box[1]}) >= y2({new_box[3]})"
                            )
                        if not is_in_bounds:
                            print("   Range issue: out of image bounds")
                        print("=== Drag debug end ===\n")

                self.drag_start_pos = current_pos

        # Pan image
        elif self.panning and self.pan_start_pos and self.image:
            current_pos = event.pos()
            dx = current_pos.x() - self.pan_start_pos.x()
            dy = current_pos.y() - self.pan_start_pos.y()

            new_offset_x = self.zoom_offset_x + dx
            new_offset_y = self.zoom_offset_y + dy

            widget_size = self.size()
            image_size = self.image.size()

            scale_x = widget_size.width() / image_size.width()
            scale_y = widget_size.height() / image_size.height()
            auto_scale = min(scale_x, scale_y, 1.0)
            current_scale = self.scale_factor if self.scale_factor != 1.0 else auto_scale

            scaled_width = int(image_size.width() * current_scale)
            scaled_height = int(image_size.height() * current_scale)

            max_offset_x = max(0, (scaled_width - widget_size.width()) // 2)
            max_offset_y = max(0, (scaled_height - widget_size.height()) // 2)

            if scaled_width > widget_size.width():
                self.zoom_offset_x = max(-max_offset_x, min(max_offset_x, new_offset_x))
            else:
                self.zoom_offset_x = 0

            if scaled_height > widget_size.height():
                self.zoom_offset_y = max(-max_offset_y, min(max_offset_y, new_offset_y))
            else:
                self.zoom_offset_y = 0

            self.pan_start_pos = current_pos
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False
            self.drag_start_pos = None
            self.drag_bbox_index = -1
            self.drag_mode = "move"
            self.resize_handle = None

            if self.panning:
                self.panning = False
                self.pan_start_pos = None
                self.setCursor(Qt.ArrowCursor)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.scale_factor = 1.0
            self.zoom_offset_x = 0
            self.zoom_offset_y = 0
            self.update()

    def wheelEvent(self, event):
        if not self.image:
            return

        delta = event.angleDelta().y()
        zoom_center_pos = self.last_click_pos if self.last_click_pos else event.pos()

        if delta > 0:
            new_scale = min(5.0, self.scale_factor * 1.1)
        else:
            new_scale = max(0.1, self.scale_factor * 0.9)

        widget_size = self.size()
        image_size = self.image.size()

        scale_x = widget_size.width() / image_size.width()
        scale_y = widget_size.height() / image_size.height()
        auto_scale = min(scale_x, scale_y, 1.0)

        current_scale = self.scale_factor if self.scale_factor != 1.0 else auto_scale
        scaled_width = int(image_size.width() * current_scale)
        scaled_height = int(image_size.height() * current_scale)
        x_offset = (widget_size.width() - scaled_width) // 2 + self.zoom_offset_x
        y_offset = (widget_size.height() - scaled_height) // 2 + self.zoom_offset_y

        center_x = (zoom_center_pos.x() - x_offset) / current_scale
        center_y = (zoom_center_pos.y() - y_offset) / current_scale

        self.scale_factor = new_scale

        new_scaled_width = int(image_size.width() * new_scale)
        new_scaled_height = int(image_size.height() * new_scale)
        new_x_offset = (widget_size.width() - new_scaled_width) // 2
        new_y_offset = (widget_size.height() - new_scaled_height) // 2

        self.zoom_offset_x = center_x * new_scale - zoom_center_pos.x() + new_x_offset
        self.zoom_offset_y = center_y * new_scale - zoom_center_pos.y() + new_y_offset

        self.update()

    def paintEvent(self, event):
        if self.image is None:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        widget_size = self.size()
        image_size = self.image.size()

        scale_x = widget_size.width() / image_size.width()
        scale_y = widget_size.height() / image_size.height()
        auto_scale = min(scale_x, scale_y, 1.0)

        current_scale = auto_scale if self.scale_factor == 1.0 else self.scale_factor

        scaled_width = int(image_size.width() * current_scale)
        scaled_height = int(image_size.height() * current_scale)
        x_offset = (widget_size.width() - scaled_width) // 2 + self.zoom_offset_x
        y_offset = (widget_size.height() - scaled_height) // 2 + self.zoom_offset_y

        painter.drawPixmap(int(x_offset), int(y_offset), scaled_width, scaled_height, self.image)

        for i, ann in enumerate(self.annotations):
            box = ann["box"]
            label = ann.get("class", "")
            label_detailed = ann.get("class_detailed", "")

            x1 = int(float(box[0]) * current_scale) + x_offset
            y1 = int(float(box[1]) * current_scale) + y_offset
            x2 = int(float(box[2]) * current_scale) + x_offset
            y2 = int(float(box[3]) * current_scale) + y_offset

            if i == self.selected_bbox:
                painter.setPen(QPen(QColor(0, 0, 255), 3))
                painter.setBrush(QColor(0, 0, 255, 50))
            else:
                painter.setPen(QPen(QColor(255, 0, 0), 2))
                painter.setBrush(Qt.NoBrush)

            painter.drawRect(int(x1), int(y1), int(x2 - x1), int(y2 - y1))

            # No visible corner handles for selected bbox (resize still works by dragging corners)

            font = QFont("Arial", 12)
            painter.setFont(font)
            painter.setPen(QPen(QColor(255, 255, 0), 1))

            # Show both class and class_detailed on the bbox.
            lines = [f"{label} {i}".strip()]
            if isinstance(label_detailed, str) and label_detailed.strip():
                lines.append(label_detailed.strip())

            fm = painter.fontMetrics()
            line_h = fm.height()
            pad_x = 5
            pad_y = 4
            text_w = max((fm.horizontalAdvance(line) for line in lines), default=0)
            text_h = line_h * len(lines)

            bg_w = text_w + pad_x * 2 + 5
            bg_h = text_h + pad_y * 2 + 2

            bg_x = int(x1)
            bg_y = int(y1 - bg_h - 4)
            # If there's no space above, draw below the top-left corner.
            if bg_y < 0:
                bg_y = int(y1 + 4)

            painter.fillRect(bg_x, bg_y, int(bg_w), int(bg_h), QColor(0, 0, 0, 180))

            # Draw each line (baseline positioning)
            text_x = bg_x + pad_x
            baseline_y = bg_y + pad_y + fm.ascent()
            for li, line in enumerate(lines):
                painter.drawText(int(text_x), int(baseline_y + li * line_h), line)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.image:
            pos = event.pos()
            image_x, image_y = self.widget_to_image_coords(pos)

            bbox_clicked = False
            for i, ann in enumerate(self.annotations):
                box = ann["box"]
                if float(box[0]) <= image_x <= float(box[2]) and float(box[1]) <= image_y <= float(box[3]):
                    handle_size = 16

                    widget_size = self.size()
                    image_size = self.image.size()

                    scale_x = widget_size.width() / image_size.width()
                    scale_y = widget_size.height() / image_size.height()
                    auto_scale = min(scale_x, scale_y, 1.0)

                    current_scale = auto_scale if self.scale_factor == 1.0 else self.scale_factor

                    scaled_width = int(image_size.width() * current_scale)
                    scaled_height = int(image_size.height() * current_scale)
                    x_offset = (widget_size.width() - scaled_width) // 2 + self.zoom_offset_x
                    y_offset = (widget_size.height() - scaled_height) // 2 + self.zoom_offset_y

                    bbox_x1 = int(float(box[0]) * current_scale) + x_offset
                    bbox_y1 = int(float(box[1]) * current_scale) + y_offset
                    bbox_x2 = int(float(box[2]) * current_scale) + x_offset
                    bbox_y2 = int(float(box[3]) * current_scale) + y_offset

                    mouse_x = event.pos().x()
                    mouse_y = event.pos().y()

                    handle_centers = {
                        "top_left": (bbox_x1, bbox_y1),
                        "top_right": (bbox_x2, bbox_y1),
                        "bottom_left": (bbox_x1, bbox_y2),
                        "bottom_right": (bbox_x2, bbox_y2),
                    }

                    handle_half_size = handle_size // 2

                    def is_in_handle_rect(mx, my, hx, hy):
                        return (
                            hx - handle_half_size <= mx <= hx + handle_half_size
                            and hy - handle_half_size <= my <= hy + handle_half_size
                        )

                    if is_in_handle_rect(
                        mouse_x, mouse_y, handle_centers["bottom_right"][0], handle_centers["bottom_right"][1]
                    ):
                        self.drag_mode = "resize"
                        self.resize_handle = "bottom_right"
                    elif is_in_handle_rect(mouse_x, mouse_y, handle_centers["top_left"][0], handle_centers["top_left"][1]):
                        self.drag_mode = "resize"
                        self.resize_handle = "top_left"
                    elif is_in_handle_rect(
                        mouse_x, mouse_y, handle_centers["top_right"][0], handle_centers["top_right"][1]
                    ):
                        self.drag_mode = "resize"
                        self.resize_handle = "top_right"
                    elif is_in_handle_rect(
                        mouse_x, mouse_y, handle_centers["bottom_left"][0], handle_centers["bottom_left"][1]
                    ):
                        self.drag_mode = "resize"
                        self.resize_handle = "bottom_left"
                    else:
                        self.drag_mode = "move"
                        self.resize_handle = None

                    self.selected_bbox = i
                    self.dragging = True
                    self.drag_start_pos = pos
                    self.drag_bbox_index = i
                    self.bbox_clicked.emit(i)
                    self.update()
                    bbox_clicked = True
                    break

            self.last_click_pos = pos

            if not bbox_clicked:
                self.panning = True
                self.pan_start_pos = pos
                self.setCursor(Qt.ClosedHandCursor)

