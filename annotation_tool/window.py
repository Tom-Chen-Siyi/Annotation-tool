from __future__ import annotations

import json
from typing import Optional, Tuple

from PIL import Image
from PyQt5.QtCore import QEvent, Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QShortcut,
    QSlider,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .config import (
    CLASS_OPTIONS,
    DETAILED_CLASS_OPTIONS,
    DEBUG,
    SESSION_STATE_PATH,
)
from .image_display import ImageDisplayWidget
from .matching import load_matched_pairs


class AnnotationToolWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.matched_pairs = load_matched_pairs()
        self.total_frames = len(self.matched_pairs)
        self.current_frame_index = 0
        self.current_annotations = []

        self.is_modified = False
        self.updating_inputs = False
        self._updating_frame_controls = False
        self._is_autosaving = False
        self._bbox_count_cache = {}

        # Autosave
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.timeout.connect(self._autosave_now)

        # Persist last position across app restarts
        self._session_state_path = SESSION_STATE_PATH
        self._session_state_timer = QTimer(self)
        self._session_state_timer.setSingleShot(True)
        self._session_state_timer.timeout.connect(self._save_session_state_now)

        if self.total_frames == 0:
            QMessageBox.critical(self, "Error", "No matching image/JSON file pairs found!")
            raise SystemExit(1)

        self.init_ui()
        state = self._load_session_state()
        if state is not None:
            frame_index, bbox_index = state
            self.load_frame(frame_index, select_bbox_index=bbox_index)
        else:
            self.load_frame(0)

    # ---------------- UI ----------------
    def init_ui(self):
        self.setWindowTitle("Image Annotation Tool")
        self.setGeometry(100, 100, 2000, 1400)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # Left: image display + bottom bar
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        self.image_display = ImageDisplayWidget()
        self.image_display.bbox_clicked.connect(self.on_bbox_clicked)
        self.image_display.bbox_modified.connect(self.on_bbox_modified)
        left_layout.addWidget(self.image_display)
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
        self.frame_slider.setFixedWidth(500)

        self.frame_prefix_label = QLabel("Frame")
        self.frame_index_input = QSpinBox()
        self.frame_index_input.setMinimum(1)
        self.frame_index_input.setMaximum(self.total_frames)
        self.frame_index_input.setValue(1)
        self.frame_index_input.setFixedWidth(110)
        self.frame_total_label = QLabel(f"/ {self.total_frames}")

        for btn in (self.prev_btn, self.next_btn):
            btn.setFixedSize(34, 30)
            btn.setFocusPolicy(Qt.NoFocus)
        self.frame_prefix_label.setFixedWidth(55)

        frame_bar_layout.addStretch(1)
        frame_bar_layout.addWidget(self.prev_btn)
        frame_bar_layout.addWidget(self.frame_slider)
        frame_bar_layout.addWidget(self.next_btn)
        frame_bar_layout.addSpacing(18)
        frame_bar_layout.addWidget(self.frame_prefix_label)
        frame_bar_layout.addWidget(self.frame_index_input)
        frame_bar_layout.addWidget(self.frame_total_label)
        frame_bar_layout.addStretch(1)

        frame_bar.setStyleSheet(
            """
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
        """
        )

        left_layout.addWidget(frame_bar, alignment=Qt.AlignHCenter)
        splitter.addWidget(left_widget)

        # Right: controls
        right_widget = QWidget()
        right_widget.setMinimumWidth(500)
        right_layout = QVBoxLayout(right_widget)

        bbox_group = QGroupBox("BBox List")
        bbox_layout = QVBoxLayout(bbox_group)
        self.bbox_list = QListWidget()
        self.bbox_list.setMaximumHeight(200)
        self.bbox_list.currentRowChanged.connect(self.on_bbox_list_selection)
        bbox_layout.addWidget(self.bbox_list)
        right_layout.addWidget(bbox_group)

        edit_group = QGroupBox("Edit")
        edit_layout = QGridLayout(edit_group)

        edit_layout.addWidget(QLabel("Class:"), 0, 0)
        self.class_input = QComboBox()
        # Class must be one of the predefined options (no free text), but still allow
        # fast keyboard search via prefix-completer + popup.
        self.class_input.setEditable(True)
        self.class_input.setInsertPolicy(QComboBox.NoInsert)
        self.class_input.addItems(CLASS_OPTIONS)
        # For strong validation (no out-of-list values).
        self._class_options_lookup = {s.strip().casefold(): s for s in CLASS_OPTIONS if isinstance(s, str) and s.strip()}
        self._last_valid_class_text = self._class_other_text()
        from PyQt5.QtWidgets import QCompleter  # local import
        self._class_completer = QCompleter(CLASS_OPTIONS, self.class_input)
        self._class_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._class_completer.setFilterMode(Qt.MatchStartsWith)
        self._class_completer.setCompletionMode(QCompleter.PopupCompletion)
        self.class_input.setCompleter(self._class_completer)
        if self.class_input.lineEdit() is not None:
            self.class_input.lineEdit().textEdited.connect(self._on_class_text_edited)
            self.class_input.lineEdit().editingFinished.connect(self._on_class_editing_finished)
        edit_layout.addWidget(self.class_input, 0, 1)

        edit_layout.addWidget(QLabel("Class Detailed:"), 2, 0)
        self.class_detailed_input = QComboBox()
        self.class_detailed_input.setEditable(True)
        self.class_detailed_input.setInsertPolicy(QComboBox.NoInsert)
        self.class_detailed_input.addItems(DETAILED_CLASS_OPTIONS)
        # For strong validation (no out-of-list values).
        self._detailed_class_options_lookup = {
            s.strip().casefold(): s for s in DETAILED_CLASS_OPTIONS if isinstance(s, str) and s.strip()
        }
        self._last_valid_class_detailed_text = ""
        from PyQt5.QtWidgets import QCompleter  # local import
        self._detailed_class_completer = QCompleter(DETAILED_CLASS_OPTIONS, self.class_detailed_input)
        self._detailed_class_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._detailed_class_completer.setFilterMode(Qt.MatchStartsWith)
        self._detailed_class_completer.setCompletionMode(QCompleter.PopupCompletion)
        self.class_detailed_input.setCompleter(self._detailed_class_completer)
        if self.class_detailed_input.lineEdit() is not None:
            self.class_detailed_input.lineEdit().textEdited.connect(self._on_detailed_class_text_edited)
            self.class_detailed_input.lineEdit().editingFinished.connect(self._on_detailed_class_editing_finished)
        edit_layout.addWidget(self.class_detailed_input, 2, 1)

        edit_layout.addWidget(QLabel("Detailed Caption:"), 3, 0)
        self.detailed_caption_input = QTextEdit()
        self.detailed_caption_input.setMinimumHeight(120)
        self.detailed_caption_input.setLineWrapMode(QTextEdit.WidgetWidth)
        # Disabled (requested): keep display but prevent editing/focus.
        self.detailed_caption_input.setDisabled(True)
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

        right_layout.addWidget(edit_group)

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

        self.status_text = QTextEdit()
        self.status_text.setMinimumHeight(100)
        self.status_text.setReadOnly(True)
        right_layout.addWidget(QLabel("Status:"))
        right_layout.addWidget(self.status_text)

        splitter.addWidget(right_widget)
        splitter.setSizes([1200, 800])

        self.connect_signals()

        # Global shortcuts
        self._shortcut_prev_bbox = QShortcut(Qt.Key_A, self)
        self._shortcut_prev_bbox.setContext(Qt.ApplicationShortcut)
        self._shortcut_prev_bbox.activated.connect(self.select_prev_bbox)

        self._shortcut_next_bbox = QShortcut(Qt.Key_D, self)
        self._shortcut_next_bbox.setContext(Qt.ApplicationShortcut)
        self._shortcut_next_bbox.activated.connect(self.select_next_bbox)

        self._shortcut_delete_bbox = QShortcut(Qt.Key_Delete, self)
        self._shortcut_delete_bbox.setContext(Qt.ApplicationShortcut)
        self._shortcut_delete_bbox.activated.connect(self.delete_bbox_shortcut)

        self._shortcut_backspace_delete_bbox = QShortcut(Qt.Key_Backspace, self)
        self._shortcut_backspace_delete_bbox.setContext(Qt.ApplicationShortcut)
        self._shortcut_backspace_delete_bbox.activated.connect(self.delete_bbox_shortcut)

        self._install_editor_focus_filters()
        self._update_shortcuts_enabled_from_focus()

    def connect_signals(self):
        self.prev_btn.clicked.connect(self.previous_frame)
        self.next_btn.clicked.connect(self.next_frame)
        self.frame_slider.valueChanged.connect(self.on_frame_slider_changed)
        self.frame_index_input.valueChanged.connect(self.on_frame_index_input_changed)

        self.add_bbox_btn.clicked.connect(self.add_bbox)
        self.delete_bbox_btn.clicked.connect(self.delete_bbox)
        self.save_btn.clicked.connect(self.save_annotations)

        self.x1_input.valueChanged.connect(self.on_coord_changed)
        self.y1_input.valueChanged.connect(self.on_coord_changed)
        self.x2_input.valueChanged.connect(self.on_coord_changed)
        self.y2_input.valueChanged.connect(self.on_coord_changed)

        self.class_input.currentTextChanged.connect(self.on_class_changed)
        self.class_detailed_input.currentTextChanged.connect(self.on_class_detailed_changed)
        self.detailed_caption_input.textChanged.connect(self.on_text_modified)

    # ---------------- Frame / selection ----------------
    def load_frame(self, frame_index: int, select_bbox_index: Optional[int] = None):
        if not (0 <= frame_index < self.total_frames):
            return

        self.flush_autosave()
        self.current_frame_index = frame_index

        img_path, json_path = self.matched_pairs[frame_index]
        self.image_display.set_image(img_path)

        try:
            with open(json_path, "r") as f:
                self.current_annotations = json.load(f)
        except Exception as e:
            self.current_annotations = []
            self.log_status(f"⚠️ Error loading annotations: {e}")

        try:
            self._bbox_count_cache[frame_index] = len(self.current_annotations) if isinstance(self.current_annotations, list) else 0
        except Exception:
            self._bbox_count_cache[frame_index] = 0

        self.is_modified = False
        self.update_ui()

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
        self._updating_frame_controls = True
        try:
            self.frame_slider.setValue(self.current_frame_index)
            self.frame_index_input.setValue(self.current_frame_index + 1)
        finally:
            self._updating_frame_controls = False

        self.update_bbox_list()
        self.image_display.set_annotations(self.current_annotations)

    def update_bbox_list(self):
        self.bbox_list.clear()
        for i, ann in enumerate(self.current_annotations):
            class_detailed = ann.get("class_detailed", "")
            detailed_caption = ann.get("detailed_caption", "")
            parts = [f"{i}:", ann.get("class", "")]
            if class_detailed:
                parts.append(f"<{class_detailed}>")
            if detailed_caption:
                short_cap = detailed_caption[:40] + ("…" if len(detailed_caption) > 40 else "")
                parts.append(f"cap={short_cap}")
            parts.append(str(ann.get("box", "")))
            self.bbox_list.addItem(" ".join(parts))

    def _refresh_bbox_list_preserve_selection(self, prefer_row: Optional[int] = None):
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
        if self._updating_frame_controls:
            return
        if value != self.current_frame_index:
            self.load_frame(value)

    def on_frame_index_input_changed(self, value: int):
        if self._updating_frame_controls:
            return
        target = int(value) - 1
        if 0 <= target < self.total_frames and target != self.current_frame_index:
            self.load_frame(target)

    def previous_frame(self):
        if self.current_frame_index > 0:
            self.load_frame(self.current_frame_index - 1)

    def next_frame(self):
        if self.current_frame_index < self.total_frames - 1:
            self.load_frame(self.current_frame_index + 1)

    def on_bbox_clicked(self, bbox_index):
        self.bbox_list.setCurrentRow(bbox_index)
        self.image_display.set_selected_bbox(bbox_index)
        self.update_inputs()
        self.schedule_session_state_save()

    def on_bbox_modified(self, bbox_index):
        if not (0 <= bbox_index < len(self.current_annotations)):
            return
        self.is_modified = True
        self._refresh_bbox_list_preserve_selection()
        self.schedule_autosave()

    def on_bbox_list_selection(self, row):
        if 0 <= row < len(self.current_annotations):
            self.image_display.set_selected_bbox(row)
            self.update_inputs()
            self.schedule_session_state_save()

    # ---------------- Editing ----------------
    def update_inputs(self):
        current_row = self.bbox_list.currentRow()
        if 0 <= current_row < len(self.current_annotations):
            bbox = self.current_annotations[current_row]
            self.updating_inputs = True

            cls = bbox.get("class", "")
            coerced = self._coerce_class_text(cls)
            self._last_valid_class_text = coerced
            self.class_input.blockSignals(True)
            self.class_input.setEditText(coerced)
            self.class_input.blockSignals(False)

            self.class_detailed_input.blockSignals(True)
            raw_cd = bbox.get("class_detailed", "")
            coerced_cd = self._coerce_detailed_class_text(raw_cd, fallback_to_last=True)
            # Keep last valid for "revert" behavior.
            self._last_valid_class_detailed_text = coerced_cd or ""
            self.class_detailed_input.setEditText(coerced_cd)
            self.class_detailed_input.blockSignals(False)

            self.detailed_caption_input.setPlainText(bbox.get("detailed_caption", ""))

            self.x1_input.valueChanged.disconnect()
            self.y1_input.valueChanged.disconnect()
            self.x2_input.valueChanged.disconnect()
            self.y2_input.valueChanged.disconnect()

            self.x1_input.setValue(int(bbox["box"][0]))
            self.y1_input.setValue(int(bbox["box"][1]))
            self.x2_input.setValue(int(bbox["box"][2]))
            self.y2_input.setValue(int(bbox["box"][3]))

            self.x1_input.valueChanged.connect(self.on_coord_changed)
            self.y1_input.valueChanged.connect(self.on_coord_changed)
            self.x2_input.valueChanged.connect(self.on_coord_changed)
            self.y2_input.valueChanged.connect(self.on_coord_changed)
            self.updating_inputs = False
        else:
            self.clear_inputs()

    def clear_inputs(self):
        self.updating_inputs = True
        self.class_input.blockSignals(True)
        self.class_input.setEditText("")
        self.class_input.blockSignals(False)
        self._last_valid_class_text = self._class_other_text()

        self.class_detailed_input.blockSignals(True)
        self.class_detailed_input.setEditText("")
        self.class_detailed_input.blockSignals(False)
        self._last_valid_class_detailed_text = ""

        self.detailed_caption_input.clear()
        self.x1_input.setValue(0)
        self.y1_input.setValue(0)
        self.x2_input.setValue(0)
        self.y2_input.setValue(0)
        self.updating_inputs = False

    def on_coord_changed(self):
        current_row = self.bbox_list.currentRow()
        if current_row < 0 or current_row >= len(self.current_annotations):
            return

        x1 = self.x1_input.value()
        y1 = self.y1_input.value()
        x2 = self.x2_input.value()
        y2 = self.y2_input.value()
        if x1 >= x2 or y1 >= y2:
            return

        self.current_annotations[current_row]["box"] = [int(x1), int(y1), int(x2), int(y2)]
        self.is_modified = True
        self.image_display.set_annotations(self.current_annotations)
        self._refresh_bbox_list_preserve_selection(prefer_row=current_row)
        self.schedule_autosave()

    def on_text_modified(self, *_args):
        if self.updating_inputs or self._is_autosaving:
            return
        self.is_modified = True
        self.schedule_autosave()

    def on_class_changed(self, _value: str):
        if self.updating_inputs or self._is_autosaving:
            return
        current_row = self.bbox_list.currentRow()
        if current_row < 0 or current_row >= len(self.current_annotations):
            return
        new_class = self.class_input.currentText().strip()
        # While typing, editable combobox can contain partial/invalid text.
        # Only commit if the text is a valid option.
        coerced = self._coerce_class_text(new_class, fallback_to_last=False)
        if coerced is None:
            return
        self._last_valid_class_text = coerced
        # Normalize UI to canonical casing from options
        self.class_input.blockSignals(True)
        self.class_input.setEditText(coerced)
        self.class_input.blockSignals(False)
        self.current_annotations[current_row]["class"] = coerced
        self.is_modified = True
        self.image_display.set_annotations(self.current_annotations)
        self._refresh_bbox_list_preserve_selection(prefer_row=current_row)
        self.image_display.set_selected_bbox(current_row)
        self.schedule_autosave()

    def on_class_detailed_changed(self, _value: str):
        if self.updating_inputs or self._is_autosaving:
            return
        current_row = self.bbox_list.currentRow()
        if current_row < 0 or current_row >= len(self.current_annotations):
            return

        raw = self.class_detailed_input.currentText().strip()
        if raw == "":
            # Allow temporary clear while re-typing; only delete on save or editingFinished.
            return

        coerced = self._coerce_detailed_class_text(raw, fallback_to_last=False)
        if coerced is None:
            return
        self._last_valid_class_detailed_text = coerced
        # Normalize UI to canonical casing from options
        self.class_detailed_input.blockSignals(True)
        self.class_detailed_input.setEditText(coerced)
        self.class_detailed_input.blockSignals(False)
        self.current_annotations[current_row]["class_detailed"] = coerced

        self.is_modified = True
        self.image_display.set_annotations(self.current_annotations)
        self._refresh_bbox_list_preserve_selection(prefer_row=current_row)
        self.image_display.set_selected_bbox(current_row)
        self.schedule_autosave()
    def _coerce_detailed_class_text(self, text: str, *, fallback_to_last: bool = True) -> Optional[str]:
        """
        Return canonical class_detailed text from options.

        - If `text` matches an option (case-insensitive), return canonical text.
        - If invalid and fallback_to_last=True, return last valid (or "" if none).
        - If invalid and fallback_to_last=False, return None (do not commit while typing).
        """
        t = (text or "").strip()
        if t:
            canonical = self._detailed_class_options_lookup.get(t.casefold())
            if canonical is not None:
                return canonical
        if not fallback_to_last:
            return None
        return (self._last_valid_class_detailed_text or "").strip()


    def _class_other_text(self) -> str:
        """Return the canonical 'Other' option if present, else first option, else empty."""
        for opt in CLASS_OPTIONS:
            if isinstance(opt, str) and opt.strip().casefold() == "other":
                return opt.strip()
        for opt in CLASS_OPTIONS:
            if isinstance(opt, str) and opt.strip():
                return opt.strip()
        return ""

    def _coerce_class_text(self, text: str, *, fallback_to_last: bool = True) -> Optional[str]:
        """
        Return canonical class text from options.

        - If `text` matches an option (case-insensitive), return that option's canonical text.
        - If not valid and fallback_to_last=True, return last valid or 'Other'.
        - If not valid and fallback_to_last=False, return None (do not commit while typing).
        """
        t = (text or "").strip()
        if t:
            canonical = self._class_options_lookup.get(t.casefold())
            if canonical is not None:
                return canonical
        if not fallback_to_last:
            return None
        return (self._last_valid_class_text or "").strip() or self._class_other_text()

    def _on_class_text_edited(self, text: str):
        """When Class input becomes empty, show all options (like Class Detailed)."""
        if self.updating_inputs:
            return
        try:
            if text.strip() == "":
                self._class_completer.setCompletionPrefix("")
                self.class_input.showPopup()
                self._class_completer.complete()
        except Exception:
            pass

    def _on_class_editing_finished(self):
        """Strong validation: on Enter / focus-out, revert invalid value to last valid / Other.

        Note: we allow the user to temporarily clear the field while re-typing.
        """
        if self.updating_inputs:
            return
        raw = self.class_input.currentText().strip()
        # Allow user to clear the field without immediately snapping back.
        if raw == "":
            return

        # Non-empty but invalid -> revert to last valid / Other.
        coerced = self._coerce_class_text(raw, fallback_to_last=True) or self._class_other_text()
        if not coerced:
            return

        self._last_valid_class_text = coerced
        self.class_input.blockSignals(True)
        self.class_input.setEditText(coerced)
        self.class_input.blockSignals(False)

        # Commit to model (and autosave) if a bbox is selected
        current_row = self.bbox_list.currentRow()
        if 0 <= current_row < len(self.current_annotations):
            if self.current_annotations[current_row].get("class", "") != coerced:
                self.current_annotations[current_row]["class"] = coerced
                self.is_modified = True
                self.image_display.set_annotations(self.current_annotations)
                self._refresh_bbox_list_preserve_selection(prefer_row=current_row)
                self.image_display.set_selected_bbox(current_row)
                self.schedule_autosave()

    def _on_detailed_class_text_edited(self, text: str):
        if self.updating_inputs:
            return
        if text.strip() == "":
            try:
                self._detailed_class_completer.setCompletionPrefix("")
                self.class_detailed_input.showPopup()
                self._detailed_class_completer.complete()
            except Exception:
                pass

    def _on_detailed_class_editing_finished(self):
        """Strong validation: allow clear; non-empty invalid -> revert to last valid (or clear)."""
        if self.updating_inputs:
            return
        raw = self.class_detailed_input.currentText().strip()
        if raw == "":
            # Allow clear while re-typing; don't snap back.
            return
        coerced = self._coerce_detailed_class_text(raw, fallback_to_last=True)
        # If invalid and no last valid, clear it.
        if coerced is None:
            coerced = ""
        self.class_detailed_input.blockSignals(True)
        self.class_detailed_input.setEditText(coerced)
        self.class_detailed_input.blockSignals(False)
        if coerced:
            self._last_valid_class_detailed_text = coerced

        # Commit to model (and autosave) if a bbox is selected
        current_row = self.bbox_list.currentRow()
        if 0 <= current_row < len(self.current_annotations):
            if coerced:
                if self.current_annotations[current_row].get("class_detailed", "") != coerced:
                    self.current_annotations[current_row]["class_detailed"] = coerced
                    self.is_modified = True
                    self.image_display.set_annotations(self.current_annotations)
                    self._refresh_bbox_list_preserve_selection(prefer_row=current_row)
                    self.image_display.set_selected_bbox(current_row)
                    self.schedule_autosave()
            else:
                # If cleared, remove the key (on editingFinished, not while typing).
                if "class_detailed" in self.current_annotations[current_row]:
                    del self.current_annotations[current_row]["class_detailed"]
                    self.is_modified = True
                    self.image_display.set_annotations(self.current_annotations)
                    self._refresh_bbox_list_preserve_selection(prefer_row=current_row)
                    self.image_display.set_selected_bbox(current_row)
                    self.schedule_autosave()

    def add_bbox(self):
        img_path, _ = self.matched_pairs[self.current_frame_index]
        with Image.open(img_path) as img:
            width, height = img.size

        center_x, center_y = width // 2, height // 2
        size = 100

        new_bbox = {
            "class": "new_object",
            "box": [
                int(center_x - size // 2),
                int(center_y - size // 2),
                int(center_x + size // 2),
                int(center_y + size // 2),
            ],
            "score": 1.0,
        }

        self.current_annotations.append(new_bbox)
        self.is_modified = True
        self._bbox_count_cache[self.current_frame_index] = len(self.current_annotations)
        self.update_ui()
        self.log_status("✅ Added new bounding box")
        self.schedule_autosave()

    def delete_bbox(self):
        current_row = self.bbox_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "Warning", "Please select a bounding box first")
            return

        deleted_class = self.current_annotations[current_row].get("class", "")
        del self.current_annotations[current_row]
        self.is_modified = True
        self._bbox_count_cache[self.current_frame_index] = len(self.current_annotations)
        self.update_ui()
        self.clear_inputs()
        self.log_status(f"✅ Deleted bounding box {current_row}: {deleted_class}")
        self.flush_autosave()

    def save_annotations(self):
        current_row = self.bbox_list.currentRow()
        if 0 <= current_row < len(self.current_annotations):
            # Strong validation before persisting: Class must be from dropdown options.
            raw = self.class_input.currentText().strip()
            if raw == "":
                coerced = self._class_other_text()
            else:
                coerced = self._coerce_class_text(raw, fallback_to_last=True) or self._class_other_text()
            if coerced:
                self._last_valid_class_text = coerced
                self.class_input.blockSignals(True)
                self.class_input.setEditText(coerced)
                self.class_input.blockSignals(False)
                self.current_annotations[current_row]["class"] = coerced
            # Strong validation before persisting: class_detailed must be from dropdown options or empty.
            cd_raw = self.class_detailed_input.currentText().strip()
            if cd_raw == "":
                cd = ""
            else:
                cd = self._coerce_detailed_class_text(cd_raw, fallback_to_last=True) or ""
                if cd:
                    self._last_valid_class_detailed_text = cd
                    self.class_detailed_input.blockSignals(True)
                    self.class_detailed_input.setEditText(cd)
                    self.class_detailed_input.blockSignals(False)
            dc = self.detailed_caption_input.toPlainText().strip()
            if cd:
                self.current_annotations[current_row]["class_detailed"] = cd
            elif "class_detailed" in self.current_annotations[current_row]:
                del self.current_annotations[current_row]["class_detailed"]
            if dc:
                self.current_annotations[current_row]["detailed_caption"] = dc
            elif "detailed_caption" in self.current_annotations[current_row]:
                del self.current_annotations[current_row]["detailed_caption"]

        for ann in self.current_annotations:
            if isinstance(ann, dict) and "openvocab" in ann:
                try:
                    del ann["openvocab"]
                except Exception:
                    pass

        _, json_path = self.matched_pairs[self.current_frame_index]
        try:
            self._is_autosaving = True
            with open(json_path, "w") as f:
                json.dump(self.current_annotations, f, indent=2)
            self.is_modified = False
            self._bbox_count_cache[self.current_frame_index] = (
                len(self.current_annotations) if isinstance(self.current_annotations, list) else 0
            )
            self._refresh_bbox_list_preserve_selection()
            self.log_status(f"✅ Saved to: {json_path.name}")
        except Exception as e:
            self.log_status(f"❌ Save failed: {e}")
        finally:
            self._is_autosaving = False

    # ---------------- Autosave / persistence ----------------
    def log_status(self, message):
        self.status_text.append(f"[{QApplication.instance().applicationName()}] {message}")
        self.status_text.ensureCursorVisible()

    def schedule_autosave(self, delay_ms: int = 250):
        if not self.is_modified:
            return
        self._autosave_timer.start(max(0, int(delay_ms)))

    def flush_autosave(self):
        if self._autosave_timer.isActive():
            self._autosave_timer.stop()
        if self.is_modified:
            self._autosave_now()

    def schedule_session_state_save(self, delay_ms: int = 300):
        self._session_state_timer.start(max(0, int(delay_ms)))

    def flush_session_state_save(self):
        if self._session_state_timer.isActive():
            self._session_state_timer.stop()
        self._save_session_state_now()

    def _save_session_state_now(self):
        try:
            bbox_row = self.bbox_list.currentRow()
            bbox_index = int(bbox_row) if bbox_row >= 0 else None
            payload = {"frame_index": int(self.current_frame_index), "bbox_index": bbox_index}
            with open(self._session_state_path, "w") as f:
                json.dump(payload, f, indent=2)
        except Exception:
            pass

    def _load_session_state(self) -> Optional[Tuple[int, Optional[int]]]:
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
        try:
            self.flush_autosave()
            self.flush_session_state_save()
        finally:
            event.accept()

    def _autosave_now(self):
        if not self.is_modified:
            return
        self.save_annotations()

    # ---------------- Shortcuts ----------------
    def _install_editor_focus_filters(self):
        widgets = []
        widgets.extend([self.class_input, self.class_detailed_input])
        if self.class_input.lineEdit() is not None:
            widgets.append(self.class_input.lineEdit())
        if self.class_detailed_input.lineEdit() is not None:
            widgets.append(self.class_detailed_input.lineEdit())
        # ComboBox popup views (focus may move here when dropdown is open)
        try:
            widgets.append(self.class_input.view())
            if self.class_input.view() is not None and self.class_input.view().viewport() is not None:
                widgets.append(self.class_input.view().viewport())
        except Exception:
            pass
        try:
            widgets.append(self.class_detailed_input.view())
            if self.class_detailed_input.view() is not None and self.class_detailed_input.view().viewport() is not None:
                widgets.append(self.class_detailed_input.view().viewport())
        except Exception:
            pass
        widgets.append(self.detailed_caption_input)
        for sb in (self.x1_input, self.y1_input, self.x2_input, self.y2_input):
            widgets.append(sb)
            try:
                if sb.lineEdit() is not None:
                    widgets.append(sb.lineEdit())
            except Exception:
                pass
        for comp in (getattr(self, "_class_completer", None), getattr(self, "_detailed_class_completer", None)):
            if comp is None:
                continue
            try:
                if comp.popup() is not None:
                    widgets.append(comp.popup())
            except Exception:
                pass
        for w in widgets:
            try:
                w.installEventFilter(self)
            except Exception:
                pass

    def _is_any_editor_focused(self) -> bool:
        fw = QApplication.focusWidget()
        if fw is None:
            return False
        # If user is editing anything in the right panel, disable shortcuts.
        if isinstance(fw, (QLineEdit, QTextEdit, QSpinBox, QComboBox)):
            return True
        # ComboBox dropdown popup views
        try:
            v = self.class_input.view()
            if v is not None and (fw is v or v.isAncestorOf(fw) or v.isVisible()):
                return True
            if v is not None and v.viewport() is not None and (fw is v.viewport() or v.viewport().isAncestorOf(fw)):
                return True
        except Exception:
            pass
        try:
            v = self.class_detailed_input.view()
            if v is not None and (fw is v or v.isAncestorOf(fw) or v.isVisible()):
                return True
            if v is not None and v.viewport() is not None and (fw is v.viewport() or v.viewport().isAncestorOf(fw)):
                return True
        except Exception:
            pass
        for w in (
            self.class_input,
            self.class_detailed_input,
            self.detailed_caption_input,
            self.x1_input,
            self.y1_input,
            self.x2_input,
            self.y2_input,
        ):
            try:
                if fw is w or w.isAncestorOf(fw):
                    return True
            except Exception:
                pass
        for comp in (getattr(self, "_class_completer", None), getattr(self, "_detailed_class_completer", None)):
            if comp is None:
                continue
            try:
                popup = comp.popup()
                if popup is not None and (fw is popup or popup.isAncestorOf(fw) or popup.isVisible()):
                    return True
            except Exception:
                pass
        return False

    def _update_shortcuts_enabled_from_focus(self):
        enabled = not self._is_any_editor_focused()
        # Navigation shortcuts
        try:
            self._shortcut_prev_bbox.setEnabled(enabled)
            self._shortcut_next_bbox.setEnabled(enabled)
        except Exception:
            pass
        # Delete shortcuts
        self._shortcut_delete_bbox.setEnabled(enabled)
        self._shortcut_backspace_delete_bbox.setEnabled(enabled)

    # Backwards-compatible name (older call sites)
    def _update_delete_shortcut_enabled_from_focus(self):
        self._update_shortcuts_enabled_from_focus()

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.FocusIn, QEvent.FocusOut):
            QTimer.singleShot(0, self._update_shortcuts_enabled_from_focus)
        return super().eventFilter(obj, event)

    def delete_bbox_shortcut(self):
        if self._is_any_editor_focused():
            return
        self.delete_bbox()

    # Cross-frame bbox navigation
    def _get_frame_bbox_count(self, frame_index: int) -> int:
        if frame_index in self._bbox_count_cache:
            return int(self._bbox_count_cache.get(frame_index, 0) or 0)
        try:
            _, json_path = self.matched_pairs[frame_index]
            with open(json_path, "r") as f:
                data = json.load(f)
            count = len(data) if isinstance(data, list) else 0
            self._bbox_count_cache[frame_index] = count
            return count
        except Exception:
            self._bbox_count_cache[frame_index] = 0
            return 0

    def _find_next_frame_with_bbox(self, start_index: int) -> Optional[int]:
        for i in range(start_index + 1, self.total_frames):
            if self._get_frame_bbox_count(i) > 0:
                return i
        return None

    def _find_prev_frame_with_bbox(self, start_index: int) -> Optional[int]:
        for i in range(start_index - 1, -1, -1):
            if self._get_frame_bbox_count(i) > 0:
                return i
        return None

    def select_prev_bbox(self):
        n = len(self.current_annotations)
        cur = self.bbox_list.currentRow()
        if n > 0 and cur > 0:
            self.bbox_list.setCurrentRow(cur - 1)
            return
        prev_frame = self._find_prev_frame_with_bbox(self.current_frame_index)
        if prev_frame is None:
            if n > 0:
                self.bbox_list.setCurrentRow(0)
            return
        self.load_frame(prev_frame, select_bbox_index=-1)

    def select_next_bbox(self):
        n = len(self.current_annotations)
        cur = self.bbox_list.currentRow()
        if n > 0 and 0 <= cur < n - 1:
            self.bbox_list.setCurrentRow(cur + 1)
            return
        next_frame = self._find_next_frame_with_bbox(self.current_frame_index)
        if next_frame is None:
            if n > 0:
                self.bbox_list.setCurrentRow(max(0, n - 1))
            return
        self.load_frame(next_frame, select_bbox_index=0)

