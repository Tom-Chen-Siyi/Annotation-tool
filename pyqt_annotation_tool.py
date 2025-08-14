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
        """设置缩放比例"""
        self.scale_factor = scale_factor
        self.update()
        

        
    def widget_to_image_coords(self, pos):
        """将窗口坐标转换为图像坐标"""
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
        """鼠标移动事件 - 处理拖拽和平移"""
        # 处理边界框拖拽
        if self.dragging and self.drag_bbox_index >= 0 and self.drag_bbox_index < len(self.annotations):
            current_pos = event.pos()
            if self.drag_start_pos:
                # 计算移动距离
                dx = current_pos.x() - self.drag_start_pos.x()
                dy = current_pos.y() - self.drag_start_pos.y()
                
                # 转换为图像坐标的移动距离
                image_dx = dx / self.scale_factor
                image_dy = dy / self.scale_factor
                

                
                # 更新边界框坐标
                bbox = self.annotations[self.drag_bbox_index]
                old_box = bbox["box"]
                
                if self.drag_mode == "move":
                    # 移动模式
                    new_box = [
                        int(float(old_box[0]) + image_dx),
                        int(float(old_box[1]) + image_dy),
                        int(float(old_box[2]) + image_dx),
                        int(float(old_box[3]) + image_dy)
                    ]
                else:
                    # 调整大小模式
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
                        # 如果坐标转换失败，保持原值
                        print(f"Coordinate conversion error: {e}")
                        new_box = list(old_box)
                
                # 确保边界框有效且不超出图像范围
                widget_size = self.size()
                image_size = self.image.size()
                
                print(f"New bounding box: {new_box}")
                print(f"Image size: {image_size.width()} x {image_size.height()}")
                
                # 检查边界框是否有效
                is_valid_size = len(new_box) == 4
                is_valid_coords = new_box[0] < new_box[2] and new_box[1] < new_box[3]
                is_in_bounds = (new_box[0] >= 0 and new_box[1] >= 0 and 
                               new_box[2] <= image_size.width() and new_box[3] <= image_size.height())
                
                print(f"BBox validation: size_valid={is_valid_size}, coords_valid={is_valid_coords}, in_bounds={is_in_bounds}")
                
                if is_valid_size and is_valid_coords and is_in_bounds:
                    try:
                        bbox["box"] = new_box
                        self.update()
                        
                        # 发送信号通知主窗口更新输入框
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
                
                # 更新起始位置
                self.drag_start_pos = current_pos
        
        # 处理图像平移
        elif self.panning and self.pan_start_pos:
            current_pos = event.pos()
            dx = current_pos.x() - self.pan_start_pos.x()
            dy = current_pos.y() - self.pan_start_pos.y()
            
            # 计算新的偏移量
            new_offset_x = self.zoom_offset_x + dx
            new_offset_y = self.zoom_offset_y + dy
            
            # 限制平移范围，防止图像被拖出视图
            widget_size = self.size()
            image_size = self.image.size()
            
            # 计算图像在当前缩放下的尺寸
            scale_x = widget_size.width() / image_size.width()
            scale_y = widget_size.height() / image_size.height()
            auto_scale = min(scale_x, scale_y, 1.0)
            current_scale = self.scale_factor if self.scale_factor != 1.0 else auto_scale
            
            scaled_width = int(image_size.width() * current_scale)
            scaled_height = int(image_size.height() * current_scale)
            
            # 计算最大允许的偏移量
            max_offset_x = max(0, (scaled_width - widget_size.width()) // 2)
            max_offset_y = max(0, (scaled_height - widget_size.height()) // 2)
            
            # 应用边界限制
            if scaled_width > widget_size.width():
                self.zoom_offset_x = max(-max_offset_x, min(max_offset_x, new_offset_x))
            else:
                self.zoom_offset_x = 0
                
            if scaled_height > widget_size.height():
                self.zoom_offset_y = max(-max_offset_y, min(max_offset_y, new_offset_y))
            else:
                self.zoom_offset_y = 0
            
            # 更新起始位置
            self.pan_start_pos = current_pos
            
            # 重绘
            self.update()
                
    def mouseReleaseEvent(self, event):
        """鼠标释放事件 - 结束拖拽和平移"""
        if event.button() == Qt.LeftButton:
            self.dragging = False
            self.drag_start_pos = None
            self.drag_bbox_index = -1
            self.drag_mode = "move"
            self.resize_handle = None
            
            # 结束平移
            if self.panning:
                self.panning = False
                self.pan_start_pos = None
                self.setCursor(Qt.ArrowCursor)  # 恢复默认光标
            
    def mouseDoubleClickEvent(self, event):
        """鼠标双击事件 - 重置缩放"""
        if event.button() == Qt.LeftButton:
            self.scale_factor = 1.0
            self.zoom_offset_x = 0
            self.zoom_offset_y = 0
            self.update()
            self.zoom_changed.emit(1.0)
            
    def wheelEvent(self, event):
        """鼠标滚轮事件 - 缩放功能"""
        if self.image:
            # 获取滚轮角度
            delta = event.angleDelta().y()
            
            # 使用上一次点击的位置作为缩放中心，如果没有则使用当前鼠标位置
            zoom_center_pos = self.last_click_pos if self.last_click_pos else event.pos()
            
            # 计算缩放因子
            if delta > 0:
                # 向上滚动，放大
                new_scale = min(5.0, self.scale_factor * 1.1)
            else:
                # 向下滚动，缩小
                new_scale = max(0.1, self.scale_factor * 0.9)
            
            # 计算缩放中心在图像上的位置（缩放前）
            widget_size = self.size()
            image_size = self.image.size()
            
            # 计算当前缩放下的偏移
            scale_x = widget_size.width() / image_size.width()
            scale_y = widget_size.height() / image_size.height()
            auto_scale = min(scale_x, scale_y, 1.0)
            
            current_scale = self.scale_factor if self.scale_factor != 1.0 else auto_scale
            scaled_width = int(image_size.width() * current_scale)
            scaled_height = int(image_size.height() * current_scale)
            x_offset = (widget_size.width() - scaled_width) // 2 + self.zoom_offset_x
            y_offset = (widget_size.height() - scaled_height) // 2 + self.zoom_offset_y
            
            # 缩放中心在图像上的位置
            center_x = (zoom_center_pos.x() - x_offset) / current_scale
            center_y = (zoom_center_pos.y() - y_offset) / current_scale
            
            # 更新缩放
            old_scale = self.scale_factor
            self.scale_factor = new_scale
            
            # 计算新的偏移量，使鼠标位置保持不变
            new_scaled_width = int(image_size.width() * new_scale)
            new_scaled_height = int(image_size.height() * new_scale)
            new_x_offset = (widget_size.width() - new_scaled_width) // 2
            new_y_offset = (widget_size.height() - new_scaled_height) // 2
            
            # 计算需要的偏移量，使缩放中心下的图像点保持不变
            self.zoom_offset_x = center_x * new_scale - zoom_center_pos.x() + new_x_offset
            self.zoom_offset_y = center_y * new_scale - zoom_center_pos.y() + new_y_offset
            
            # 更新显示
            self.update()
            
            # 发送缩放信号
            self.zoom_changed.emit(new_scale)
        
    def paintEvent(self, event):
        """绘制事件"""
        if self.image is None:
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 计算缩放和居中
        widget_size = self.size()
        image_size = self.image.size()
        
        # 计算缩放比例（支持自定义缩放）
        scale_x = widget_size.width() / image_size.width()
        scale_y = widget_size.height() / image_size.height()
        auto_scale = min(scale_x, scale_y, 1.0)
        
        # 使用自定义缩放或自动缩放
        if self.scale_factor == 1.0:
            current_scale = auto_scale
        else:
            current_scale = self.scale_factor
        
        # 计算居中位置（考虑缩放偏移）
        scaled_width = int(image_size.width() * current_scale)
        scaled_height = int(image_size.height() * current_scale)
        x_offset = (widget_size.width() - scaled_width) // 2 + self.zoom_offset_x
        y_offset = (widget_size.height() - scaled_height) // 2 + self.zoom_offset_y
        
        # 绘制图像
        painter.drawPixmap(int(x_offset), int(y_offset), scaled_width, scaled_height, self.image)
        
        # 绘制边界框
        for i, ann in enumerate(self.annotations):
            box = ann["box"]
            label = ann["class"]
            
            # 缩放坐标（确保坐标是数字类型）
            x1 = int(float(box[0]) * current_scale) + x_offset
            y1 = int(float(box[1]) * current_scale) + y_offset
            x2 = int(float(box[2]) * current_scale) + x_offset
            y2 = int(float(box[3]) * current_scale) + y_offset
            

            
            # 绘制矩形 - 只有选中的边界框有填充
            if i == self.selected_bbox:
                # 选中的边界框：蓝色边框，半透明蓝色填充
                painter.setPen(QPen(QColor(0, 0, 255), 3))
                painter.setBrush(QColor(0, 0, 255, 50))  # 半透明蓝色填充
            else:
                # 普通边界框：红色边框，无填充
                painter.setPen(QPen(QColor(255, 0, 0), 2))
                painter.setBrush(Qt.NoBrush)  # 无填充
            
            painter.drawRect(int(x1), int(y1), int(x2 - x1), int(y2 - y1))
            
            # 如果是选中的边界框，绘制调整手柄
            if i == self.selected_bbox:
                handle_size = 16  # 增大手柄大小，与检测区域保持一致
                # 绘制四个角的调整手柄
                painter.setPen(QPen(QColor(255, 255, 0), 2))
                painter.setBrush(QColor(255, 255, 0))
                
                # 计算手柄位置
                handle_positions = {
                    "top_left": (int(x1 - handle_size//2), int(y1 - handle_size//2)),
                    "top_right": (int(x2 - handle_size//2), int(y1 - handle_size//2)),
                    "bottom_left": (int(x1 - handle_size//2), int(y2 - handle_size//2)),
                    "bottom_right": (int(x2 - handle_size//2), int(y2 - handle_size//2))
                }
                
                # 绘制手柄
                for handle_name, (hx, hy) in handle_positions.items():
                    painter.drawRect(hx, hy, handle_size, handle_size)
            
            # 绘制标签
            font = QFont("Arial", 10)
            painter.setFont(font)
            painter.setPen(QPen(QColor(255, 255, 0), 1))
            
            # 标签背景
            text_rect = painter.fontMetrics().boundingRect(f"{label} {i}")
            painter.fillRect(int(x1), int(y1 - text_rect.height() - 5), 
                           text_rect.width() + 10, text_rect.height() + 5, 
                           QColor(0, 0, 0, 180))
            
            # 绘制文本
            painter.drawText(int(x1 + 5), int(y1 - 5), f"{label} {i}")
    
    def mousePressEvent(self, event):
        """鼠标点击事件"""
        if event.button() == Qt.LeftButton and self.image:
            # 获取点击位置
            pos = event.pos()
            image_x, image_y = self.widget_to_image_coords(pos)
            
            # 检查是否点击了边界框或调整手柄
            bbox_clicked = False
            for i, ann in enumerate(self.annotations):
                box = ann["box"]
                # 确保坐标是数字类型进行比较
                if (float(box[0]) <= image_x <= float(box[2]) and 
                    float(box[1]) <= image_y <= float(box[3])):
                    
                    # 检查是否点击了调整手柄
                    handle_size = 16  # 进一步增大手柄检测区域，提高检测成功率
                    
                    # 统计点击次数
                    self.handle_click_stats["total"] += 1
                    
                    # 计算手柄在窗口坐标中的位置（与绘制代码保持一致）
                    widget_size = self.size()
                    image_size = self.image.size()
                    
                    # 使用与绘制相同的缩放计算方式
                    scale_x = widget_size.width() / image_size.width()
                    scale_y = widget_size.height() / image_size.height()
                    auto_scale = min(scale_x, scale_y, 1.0)
                    
                    # 使用自定义缩放或自动缩放（与绘制代码一致）
                    if self.scale_factor == 1.0:
                        current_scale = auto_scale
                    else:
                        current_scale = self.scale_factor
                    
                    scaled_width = int(image_size.width() * current_scale)
                    scaled_height = int(image_size.height() * current_scale)
                    x_offset = (widget_size.width() - scaled_width) // 2 + self.zoom_offset_x
                    y_offset = (widget_size.height() - scaled_height) // 2 + self.zoom_offset_y
                    
                    # 计算边界框在窗口坐标中的位置
                    bbox_x1 = int(float(box[0]) * current_scale) + x_offset
                    bbox_y1 = int(float(box[1]) * current_scale) + y_offset
                    bbox_x2 = int(float(box[2]) * current_scale) + x_offset
                    bbox_y2 = int(float(box[3]) * current_scale) + y_offset
                    
                    # 检查点击位置
                    mouse_x = event.pos().x()
                    mouse_y = event.pos().y()
                    
                    # 检查四个角的手柄（使用更大的检测区域）
                    
                    # 计算各手柄中心位置（与绘制位置一致）
                    handle_centers = {
                        "top_left": (bbox_x1, bbox_y1),
                        "top_right": (bbox_x2, bbox_y1),
                        "bottom_left": (bbox_x1, bbox_y2),
                        "bottom_right": (bbox_x2, bbox_y2)
                    }
                    
                    # 使用手柄中心位置进行检测（矩形区域检测）
                    handle_half_size = handle_size // 2
                    
                    # 检查鼠标是否在手柄的矩形区域内
                    def is_in_handle_rect(mx, my, hx, hy):
                        return (hx - handle_half_size <= mx <= hx + handle_half_size and 
                                hy - handle_half_size <= my <= hy + handle_half_size)
                    
                    if is_in_handle_rect(mouse_x, mouse_y, handle_centers["bottom_right"][0], handle_centers["bottom_right"][1]):
                        # 点击右下角调整手柄
                        self.drag_mode = "resize"
                        self.resize_handle = "bottom_right"
                        self.handle_click_stats["detected"] += 1
                    elif is_in_handle_rect(mouse_x, mouse_y, handle_centers["top_left"][0], handle_centers["top_left"][1]):
                        # 点击左上角调整手柄
                        self.drag_mode = "resize"
                        self.resize_handle = "top_left"
                        self.handle_click_stats["detected"] += 1
                    elif is_in_handle_rect(mouse_x, mouse_y, handle_centers["top_right"][0], handle_centers["top_right"][1]):
                        # 点击右上角调整手柄
                        self.drag_mode = "resize"
                        self.resize_handle = "top_right"
                        self.handle_click_stats["detected"] += 1
                    elif is_in_handle_rect(mouse_x, mouse_y, handle_centers["bottom_left"][0], handle_centers["bottom_left"][1]):
                        # 点击左下角调整手柄
                        self.drag_mode = "resize"
                        self.resize_handle = "bottom_left"
                        self.handle_click_stats["detected"] += 1
                    else:
                        # 点击边界框内部，进行移动
                        self.drag_mode = "move"
                        self.resize_handle = None
                    
                    self.selected_bbox = i
                    self.dragging = True
                    self.drag_start_pos = pos
                    self.drag_bbox_index = i
                    self.bbox_clicked.emit(i)
                    self.update()  # 重绘
                    bbox_clicked = True
                    break
            
            # 记录点击位置（用于缩放中心）
            self.last_click_pos = pos
            
            # 如果没有点击边界框，则开始平移图像
            if not bbox_clicked:
                self.panning = True
                self.pan_start_pos = pos
                self.setCursor(Qt.ClosedHandCursor)  # 设置手型光标

# === 主窗口 ===
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
        """初始化用户界面"""
        self.setWindowTitle("🎯 PyQt Image Annotation Tool")
        self.setGeometry(100, 100, 2000, 1400)  # 进一步增大窗口尺寸
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QHBoxLayout(central_widget)
        
        # 创建分割器
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # 左侧图像显示区域
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        # 图像显示组件
        self.image_display = ImageDisplayWidget()
        self.image_display.bbox_clicked.connect(self.on_bbox_clicked)
        self.image_display.zoom_changed.connect(self.on_zoom_changed)
        left_layout.addWidget(self.image_display)
        
        # 添加弹性空间，让图像显示区域占据更多空间
        left_layout.addStretch()
        
        # 简化的帧控制（更紧凑，放在底部）
        frame_control_layout = QHBoxLayout()
        
        self.prev_btn = QPushButton("⬅️")
        self.next_btn = QPushButton("➡️")
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setMinimum(0)
        self.frame_slider.setMaximum(self.total_frames - 1)
        self.frame_label = QLabel(f"Frame 1/{self.total_frames}")
        
        # 设置按钮和标签的最小尺寸
        self.prev_btn.setMaximumWidth(40)
        self.next_btn.setMaximumWidth(40)
        self.frame_label.setMaximumWidth(80)
        
        frame_control_layout.addWidget(self.prev_btn)
        frame_control_layout.addWidget(self.frame_slider)
        frame_control_layout.addWidget(self.next_btn)
        frame_control_layout.addWidget(self.frame_label)
        
        left_layout.addLayout(frame_control_layout)
        
        # 缩放控制（隐藏显示但保留功能）
        self.zoom_label = QLabel("Zoom: 100% (Mouse wheel to zoom, Drag to pan, Double-click to reset)")
        # 不添加到布局中，但保留引用以支持缩放功能
        
        # 文件信息（移除以节省空间）
        # self.file_info_label = QLabel("File Information")
        # left_layout.addWidget(self.file_info_label)
        
        splitter.addWidget(left_widget)
        
        # 设置分割器比例，让左侧图像区域更大
        splitter.setSizes([1200, 300])  # 左侧1200像素，右侧300像素
        
        # 右侧控制面板
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # 标注框列表（简化标题）
        bbox_group = QGroupBox("📋 BBox List")
        bbox_layout = QVBoxLayout(bbox_group)
        
        self.bbox_list = QListWidget()
        # 移除高度限制，让列表撑满整个GroupBox
        self.bbox_list.currentRowChanged.connect(self.on_bbox_list_selection)
        bbox_layout.addWidget(self.bbox_list)
        
        right_layout.addWidget(bbox_group)
        
        # 编辑控件（简化标题和标签）
        edit_group = QGroupBox("✏️ Edit")
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
        
        # 编辑按钮
        button_layout = QHBoxLayout()
        self.rename_btn = QPushButton("Rename")
        button_layout.addWidget(self.rename_btn)
        edit_layout.addLayout(button_layout, 5, 0, 1, 2)
        
        right_layout.addWidget(edit_group)
        
        # 操作按钮（简化标题）
        operation_group = QGroupBox("🛠️ Actions")
        operation_layout = QVBoxLayout(operation_group)
        
        operation_button_layout = QHBoxLayout()
        self.add_bbox_btn = QPushButton("Add")
        self.delete_bbox_btn = QPushButton("Delete")
        operation_button_layout.addWidget(self.add_bbox_btn)
        operation_button_layout.addWidget(self.delete_bbox_btn)
        operation_layout.addLayout(operation_button_layout)
        
        self.save_btn = QPushButton("💾 Save")
        operation_layout.addWidget(self.save_btn)
        
        right_layout.addWidget(operation_group)
        
        # 导出功能（简化标题）
        export_group = QGroupBox("📤 Export")
        export_layout = QVBoxLayout(export_group)
        
        self.export_json_btn = QPushButton("Export JSON")
        export_layout.addWidget(self.export_json_btn)
        
        # 导出选项
        self.export_format_combo = QComboBox()
        self.export_format_combo.addItems(["Current Frame", "All Frames"])
        export_layout.addWidget(QLabel("Range:"))
        export_layout.addWidget(self.export_format_combo)
        
        right_layout.addWidget(export_group)
        
        # 状态显示（简化）
        self.status_text = QTextEdit()
        self.status_text.setMaximumHeight(50)  # 进一步减小状态区域高度
        self.status_text.setReadOnly(True)
        right_layout.addWidget(QLabel("Status:"))
        right_layout.addWidget(self.status_text)
        
        splitter.addWidget(right_widget)
        
        # 设置分割器比例 - 让左侧图像区域更大
        splitter.setSizes([1500, 250])  # 左侧1500像素，右侧250像素
        
        # 连接信号
        self.connect_signals()
        
    def connect_signals(self):
        """连接信号和槽"""
        self.prev_btn.clicked.connect(self.previous_frame)
        self.next_btn.clicked.connect(self.next_frame)
        self.frame_slider.valueChanged.connect(self.on_frame_slider_changed)
        
        self.rename_btn.clicked.connect(self.rename_bbox)
        self.add_bbox_btn.clicked.connect(self.add_bbox)
        self.delete_bbox_btn.clicked.connect(self.delete_bbox)
        self.save_btn.clicked.connect(self.save_annotations)
        
        self.export_json_btn.clicked.connect(self.export_json)
        
        # 连接坐标输入框的实时更新信号
        self.x1_input.valueChanged.connect(self.on_coord_changed)
        self.y1_input.valueChanged.connect(self.on_coord_changed)
        self.x2_input.valueChanged.connect(self.on_coord_changed)
        self.y2_input.valueChanged.connect(self.on_coord_changed)
        
        # 缩放控制信号已通过鼠标滚轮实现
        
    def load_frame(self, frame_index):
        """加载指定帧"""
        if 0 <= frame_index < self.total_frames:
            self.current_frame_index = frame_index
            
            # 加载图像
            img_path, json_path = self.matched_pairs[frame_index]
            self.image_display.set_image(img_path)
            
            # 加载标注
            try:
                with open(json_path, 'r') as f:
                    self.current_annotations = json.load(f)
            except Exception as e:
                self.current_annotations = []
                self.log_status(f"⚠️ Error loading annotations: {e}")
            
            # 更新界面
            self.update_ui()
            self.log_status(f"✅ Loaded frame {frame_index + 1}: {img_path.name}")
            
    def update_ui(self):
        """更新用户界面"""
        # 更新帧信息
        self.frame_label.setText(f"Frame {self.current_frame_index + 1}/{self.total_frames}")
        self.frame_slider.setValue(self.current_frame_index)
        
        # 更新文件信息（已移除显示）
        # img_path, json_path = self.matched_pairs[self.current_frame_index]
        # self.file_info_label.setText(f"Image: {img_path.name}\nJSON: {json_path.name}")
        
        # 更新标注框列表
        self.update_bbox_list()
        
        # 更新图像显示
        self.image_display.set_annotations(self.current_annotations)
        
        # 确保没有选中的边界框（初始状态）
        self.image_display.set_selected_bbox(-1)
        
    def update_bbox_list(self):
        """更新标注框列表"""
        self.bbox_list.clear()
        for i, ann in enumerate(self.current_annotations):
            self.bbox_list.addItem(f"{i}: {ann['class']} {ann['box']}")
            
    def on_frame_slider_changed(self, value):
        """帧滑块改变事件"""
        if value != self.current_frame_index:
            self.load_frame(value)
            
    def previous_frame(self):
        """上一帧"""
        if self.current_frame_index > 0:
            self.load_frame(self.current_frame_index - 1)
            
    def next_frame(self):
        """下一帧"""
        if self.current_frame_index < self.total_frames - 1:
            self.load_frame(self.current_frame_index + 1)
            
    def on_bbox_clicked(self, bbox_index):
        """边界框点击事件"""
        self.bbox_list.setCurrentRow(bbox_index)
        self.image_display.set_selected_bbox(bbox_index)
        self.update_inputs()
        
    def on_zoom_changed(self, scale_factor):
        """缩放变化事件"""
        self.zoom_label.setText(f"Zoom: {int(scale_factor * 100)}%")
        
    def on_coord_changed(self):
        """坐标输入框变化事件 - 实时更新边界框"""
        current_row = self.bbox_list.currentRow()
        if current_row < 0 or current_row >= len(self.current_annotations):
            return
            
        # 获取当前输入的值
        x1 = self.x1_input.value()
        y1 = self.y1_input.value()
        x2 = self.x2_input.value()
        y2 = self.y2_input.value()
        
        # 验证坐标有效性
        if x1 >= x2 or y1 >= y2:
            return  # 无效坐标，不更新
            
        # 更新当前边界框的坐标
        self.current_annotations[current_row]['box'] = [int(x1), int(y1), int(x2), int(y2)]
        
        # 实时更新图像显示
        self.image_display.set_annotations(self.current_annotations)
        
        # 更新列表显示
        self.update_bbox_list()
        
        # 保持当前选中状态
        self.bbox_list.setCurrentRow(current_row)
        

        
    def on_bbox_list_selection(self, row):
        """标注框列表选择事件"""
        if 0 <= row < len(self.current_annotations):
            self.image_display.set_selected_bbox(row)
            self.update_inputs()
            
    def update_inputs(self):
        """更新输入框"""
        current_row = self.bbox_list.currentRow()
        if 0 <= current_row < len(self.current_annotations):
            bbox = self.current_annotations[current_row]
            self.class_input.setText(bbox['class'])
            
            # 临时断开信号连接，避免触发实时更新
            self.x1_input.valueChanged.disconnect()
            self.y1_input.valueChanged.disconnect()
            self.x2_input.valueChanged.disconnect()
            self.y2_input.valueChanged.disconnect()
            
            # 将浮点数转换为整数
            self.x1_input.setValue(int(bbox['box'][0]))
            self.y1_input.setValue(int(bbox['box'][1]))
            self.x2_input.setValue(int(bbox['box'][2]))
            self.y2_input.setValue(int(bbox['box'][3]))
            
            # 重新连接信号
            self.x1_input.valueChanged.connect(self.on_coord_changed)
            self.y1_input.valueChanged.connect(self.on_coord_changed)
            self.x2_input.valueChanged.connect(self.on_coord_changed)
            self.y2_input.valueChanged.connect(self.on_coord_changed)
        else:
            self.clear_inputs()
            
    def clear_inputs(self):
        """清空输入框"""
        self.class_input.clear()
        self.x1_input.setValue(0)
        self.y1_input.setValue(0)
        self.x2_input.setValue(0)
        self.y2_input.setValue(0)
        

    def rename_bbox(self):
        """重命名边界框"""
        current_row = self.bbox_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "Warning", "Please select a bounding box first")
            return
            
        new_class = self.class_input.text().strip()
        if not new_class:
            QMessageBox.warning(self, "Warning", "Please enter a class name")
            return
            
        self.current_annotations[current_row]['class'] = new_class
        
        # 只更新图像显示和列表，不清空输入框
        self.image_display.set_annotations(self.current_annotations)
        self.update_bbox_list()
        
        self.log_status(f"✅ Renamed bounding box {current_row} to: {new_class}")
        
    def add_bbox(self):
        """添加边界框"""
        # 获取图像尺寸
        img_path, _ = self.matched_pairs[self.current_frame_index]
        with Image.open(img_path) as img:
            width, height = img.size
            
        # 在图像中心添加边界框
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
        """删除边界框"""
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
        """保存标注"""
        _, json_path = self.matched_pairs[self.current_frame_index]
        try:
            with open(json_path, 'w') as f:
                json.dump(self.current_annotations, f, indent=2)
            self.log_status(f"✅ Saved to: {json_path.name}")
        except Exception as e:
            self.log_status(f"❌ Save failed: {e}")
            
    def export_json(self):
        """导出JSON格式"""
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
        
        # 选择保存路径
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
        """记录状态信息"""
        self.status_text.append(f"[{QApplication.instance().applicationName()}] {message}")
        self.status_text.ensureCursorVisible()
        


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PyQt Annotation Tool")
    
    # 检查依赖
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
