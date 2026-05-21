from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget, 
    QListWidgetItem, QPushButton, QStackedWidget, QLabel, QCheckBox,
    QLineEdit, QSpinBox, QDoubleSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QInputDialog, QMessageBox, QSlider, QComboBox, QColorDialog, QDialog,
    QApplication, QButtonGroup, QMenu, QGridLayout, QAbstractItemView, QStyledItemDelegate
)
from PyQt6.QtCore import Qt, QSettings, pyqtSignal, QTimer, QPoint, QRect, QThread, QVariantAnimation, QEasingCurve
from PyQt6.QtGui import QPainter, QPen, QPixmap, QColor, QBrush, QImage, QAction, QKeySequence, QIntValidator
import os
import shutil
import json
import time
import mss
import cv2
import numpy as np
import pyautogui
import re
import math
import ctypes

class HelpPopup(QDialog):
    def __init__(self, parent, title, text):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Popup)
        
        # Стилизация под темную тему с фиолетовой рамкой и закругленными углами
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e2e;
                border: 2px solid #cba6f7;
                border-radius: 8px;
            }
            QLabel {
                color: #cdd6f4;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)
        
        title_label = QLabel(f"<b>{title}</b>")
        title_label.setStyleSheet("font-size: 16px; color: #f9e2af; font-weight: bold;")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)
        
        desc_label = QLabel(text)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("font-size: 14px; line-height: 1.35;")
        layout.addWidget(desc_label)
        
        self.setMinimumWidth(350)
        self.setMaximumWidth(400)
        
        # Центрируем относительно родителя
        if parent:
            self.adjustSize()
            parent_rect = parent.rect()
            global_center = parent.mapToGlobal(parent_rect.center())
            self.move(global_center.x() - self.width() // 2, global_center.y() - self.height() // 2)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.accept()

class GlobalHotkeyThread(QThread):
    hotkey_triggered = pyqtSignal()
    
    def run(self):
        VK_CONTROL = 0x11
        ctrl_presses = 0
        last_press_time = 0
        
        try:
            user32 = ctypes.windll.user32
        except Exception:
            return # На случай запуска не на Windows
            
        while True:
            try:
                state = user32.GetAsyncKeyState(VK_CONTROL)
                is_down = bool(state & 0x8000)
                
                if is_down:
                    current_time = time.time()
                    if current_time - last_press_time > 0.15: # Защита от дребезга контактов
                        if current_time - last_press_time < 1.2:
                            ctrl_presses += 1
                        else:
                            ctrl_presses = 1
                        last_press_time = current_time
                        print(f"DEBUG HOTKEY: Ctrl pressed {ctrl_presses}/5")
                        
                        if ctrl_presses >= 5:
                            print("DEBUG HOTKEY: EMERGENCY STOP TRIGGERED!")
                            self.hotkey_triggered.emit()
                            ctrl_presses = 0
                    
                    # Ожидаем отпускания клавиши
                    while bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000):
                        time.sleep(0.05)
            except Exception:
                pass
            time.sleep(0.05)

from src.detection.map_recorder import MapRecorder
from src.tools.navigation import PathFinder
from .overlays import PickerOverlay, TestOverlay, RegionPickerOverlay

from PyQt6.QtCore import QThread, pyqtSignal as Signal

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "assets")
SCREENSHOTS_DIR = os.path.join(ASSETS_DIR, "coord_screenshots")
if not os.path.exists(SCREENSHOTS_DIR):
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

class FullScreenImageViewer(QLabel):
    def __init__(self, pixmap, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setPixmap(pixmap)
        self.setScaledContents(True)
        self.showFullScreen()
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        self.close()

class FilterHeader(QHeaderView):
    filter_requested = pyqtSignal(int, str, object) # index, action, value

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setSectionsClickable(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def paintSection(self, painter, rect, logicalIndex):
        painter.save()
        super().paintSection(painter, rect, logicalIndex)
        painter.restore()

        # Рисуем иконку фильтра (лупу) в правой части секции
        icon_size = 16
        icon_rect = QRect(rect.right() - icon_size - 5, 
                          rect.center().y() - icon_size // 2, 
                          icon_size, icon_size)
        
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#cba6f7"), 2)
        painter.setPen(pen)
        
        # Рисуем стилизованную лупу или воронку
        # Кружок лупы
        painter.drawEllipse(icon_rect.left(), icon_rect.top(), 10, 10)
        # Ручка лупы
        painter.drawLine(icon_rect.left() + 8, icon_rect.top() + 8, icon_rect.right(), icon_rect.bottom())
        painter.restore()

    def mousePressEvent(self, event):
        index = self.logicalIndexAt(event.pos())
        if index != -1:
            # Проверяем, нажал ли пользователь в область иконки (правые 25 пикселей)
            rect = QRect(self.sectionViewportPosition(index), 0, self.sectionSize(index), self.height())
            icon_area = QRect(rect.right() - 25, 0, 25, self.height())
            
            if event.button() == Qt.MouseButton.LeftButton:
                if icon_area.contains(event.pos()):
                    self.show_filter_menu(index, event.globalPosition().toPoint())
                    return
            elif event.button() == Qt.MouseButton.RightButton:
                self.show_filter_menu(index, event.globalPosition().toPoint())
                return
                
        super().mousePressEvent(event)

    def show_filter_menu(self, index, pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #313244;
            }
            QMenu::item:selected {
                background-color: #45475a;
            }
        """)

        # Сортировка
        sort_asc = menu.addAction("Сортировать: А-Я")
        sort_desc = menu.addAction("Сортировать: Я-А")
        menu.addSeparator()
        
        # Фильтры
        filter_contains = menu.addAction("Содержит...")
        filter_not_contains = menu.addAction("Не содержит...")
        filter_clear = menu.addAction("Очистить фильтр")

        action = menu.exec(pos)
        
        if action == sort_asc:
            self.filter_requested.emit(index, "sort", Qt.SortOrder.AscendingOrder)
        elif action == sort_desc:
            self.filter_requested.emit(index, "sort", Qt.SortOrder.DescendingOrder)
        elif action == filter_contains:
            text, ok = QInputDialog.getText(self, "Фильтр", "Содержит:")
            if ok: self.filter_requested.emit(index, "filter_contains", text)
        elif action == filter_not_contains:
            text, ok = QInputDialog.getText(self, "Фильтр", "Не содержит:")
            if ok: self.filter_requested.emit(index, "filter_not_contains", text)
        elif action == filter_clear:
            self.filter_requested.emit(index, "clear", None)

class CellWrapper(QWidget):
    def __init__(self, widget):
        super().__init__()
        self.inner_widget = widget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignBottom)
        layout.addWidget(widget)

def get_inner_widget(widget):
    if isinstance(widget, CellWrapper):
        return widget.inner_widget
    return widget

class TransparentTextDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.text = ""

class CoordCellWidget(QWidget):
    def __init__(self, x, y, on_changed_callback, parent=None):
        super().__init__(parent)
        self.on_changed_callback = on_changed_callback
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        self.lbl_x = QLabel("X:")
        self.lbl_x.setStyleSheet("color: #a6adc8; font-size: 14px;")
        
        self.edit_x = QLineEdit(str(x))
        self.edit_x.setFixedWidth(50)
        self.edit_x.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: #cdd6f4;
                font-size: 14px;
                padding: 0px;
            }
            QLineEdit:focus {
                background-color: #313244;
                border-radius: 2px;
                color: #f5c2e7;
            }
        """)
        self.edit_x.setValidator(QIntValidator(0, 99999))
        self.edit_x.editingFinished.connect(self.on_editing_finished)
        
        self.lbl_y = QLabel(" Y:")
        self.lbl_y.setStyleSheet("color: #a6adc8; font-size: 14px;")
        
        self.edit_y = QLineEdit(str(y))
        self.edit_y.setFixedWidth(50)
        self.edit_y.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: #cdd6f4;
                font-size: 14px;
                padding: 0px;
            }
            QLineEdit:focus {
                background-color: #313244;
                border-radius: 2px;
                color: #f5c2e7;
            }
        """)
        self.edit_y.setValidator(QIntValidator(0, 99999))
        self.edit_y.editingFinished.connect(self.on_editing_finished)
        
        layout.addWidget(self.lbl_x)
        layout.addWidget(self.edit_x)
        layout.addWidget(self.lbl_y)
        layout.addWidget(self.edit_y)
        
        self._last_x = str(x)
        self._last_y = str(y)

    def get_values(self):
        try:
            x = int(self.edit_x.text()) if self.edit_x.text() else 0
        except ValueError:
            x = 0
        try:
            y = int(self.edit_y.text()) if self.edit_y.text() else 0
        except ValueError:
            y = 0
        return x, y

    def set_values(self, x, y):
        self.edit_x.setText(str(x))
        self.edit_y.setText(str(y))
        self._last_x = str(x)
        self._last_y = str(y)

    def on_editing_finished(self):
        curr_x = self.edit_x.text()
        curr_y = self.edit_y.text()
        if curr_x != self._last_x or curr_y != self._last_y:
            self._last_x = curr_x
            self._last_y = curr_y
            self.on_changed_callback()

    def mouseDoubleClickEvent(self, event):
        x_val, y_val = self.get_values()
        text_to_copy = f"X: {x_val}, Y: {y_val}"
        QApplication.clipboard().setText(text_to_copy)
        
        table = self.parent_widget_of_type(QTableWidget)
        if table:
            pos = self.mapTo(table, event.position().toPoint())
            index = table.indexAt(pos)
            if index.isValid():
                table.setCurrentCell(index.row(), index.column())
                
        super().mouseDoubleClickEvent(event)

    def parent_widget_of_type(self, widget_type):
        p = self.parent()
        while p:
            if isinstance(p, widget_type):
                return p
            p = p.parent()
        return None

class CoordTableWidget(QTableWidget):
    def __init__(self, rows, columns, parent_page=None):
        super().__init__(rows, columns)
        self.parent_page = parent_page
        self.current_drop_row = None
        self.dragged_source_row = None
        self.animate_entry_row = None
        self.animating_rows = {}
        
        # Настройка Drag and Drop для перемещения строк
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropOverwriteMode(False)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    def startDrag(self, supportedActions):
        self.dragged_source_row = self.currentRow()
        
        # Запускаем анимацию сжатия строки источника через 50мс,
        # чтобы Qt успел сделать качественный снимок строки для курсора
        QTimer.singleShot(50, self.shrink_source_row)
        
        super().startDrag(supportedActions)
        self.reset_all_row_heights()

    def shrink_source_row(self):
        if hasattr(self, 'dragged_source_row') and self.dragged_source_row is not None:
            if 0 <= self.dragged_source_row < self.rowCount():
                self.animate_row_height(self.dragged_source_row, 0)

    def animate_row_height(self, row, target_height):
        if row < 0 or row >= self.rowCount():
            return
            
        current_anim = self.animating_rows.get(row)
        if current_anim:
            if current_anim.endValue() == target_height:
                return
            current_anim.stop()
            
        start_height = self.rowHeight(row)
        anim = QVariantAnimation(self)
        anim.setStartValue(start_height)
        anim.setEndValue(target_height)
        anim.setDuration(120)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        def update_height(val):
            if row < self.rowCount():
                self.setRowHeight(row, val)
                
        anim.valueChanged.connect(update_height)
        anim.finished.connect(lambda: self.animating_rows.pop(row, None))
        
        self.animating_rows[row] = anim
        anim.start()

    def reset_all_row_heights(self):
        for anim in list(self.animating_rows.values()):
            anim.stop()
        self.animating_rows.clear()
        
        default_h = self.verticalHeader().defaultSectionSize()
        for r in range(self.rowCount()):
            self.setRowHeight(r, default_h)
        self.current_drop_row = None
        self.viewport().update()

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-qabstractitemmodeldatalist"):
            event.acceptProposedAction()
            self.current_drop_row = None
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-qabstractitemmodeldatalist"):
            event.acceptProposedAction()
            
            pos = event.position().toPoint()
            index = self.indexAt(pos)
            row = index.row()
            
            default_h = self.verticalHeader().defaultSectionSize()
            
            # Находим целевую строку для сброса
            if row >= 0:
                rect = self.visualRect(index)
                if pos.y() < rect.y() + rect.height() / 2:
                    drop_row = row
                else:
                    drop_row = row + 1
            else:
                total_height = 0
                for r in range(self.rowCount()):
                    total_height += self.rowHeight(r)
                if pos.y() >= total_height:
                    drop_row = self.rowCount()
                else:
                    drop_row = 0
                    
            if drop_row != self.current_drop_row:
                old_drop_row = self.current_drop_row
                self.current_drop_row = drop_row
                
                # Сворачиваем старую раздвинутую строку
                if old_drop_row is not None and old_drop_row < self.rowCount():
                    self.animate_row_height(old_drop_row, default_h)
                    
                # Раздвигаем новую строку (создаем свободное пространство для визуального эффекта)
                if drop_row < self.rowCount():
                    self.animate_row_height(drop_row, default_h + 24)
                
                self.viewport().update()
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self.reset_all_row_heights()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        source_row = self.currentRow()
        dest_row = self.current_drop_row
        
        self.reset_all_row_heights()
        
        if source_row >= 0 and dest_row is not None:
            # Корректируем dest_row с учетом pop()
            if dest_row > source_row:
                dest_row -= 1
                
            if 0 <= dest_row < self.rowCount() and source_row != dest_row:
                if hasattr(self, "parent_page") and self.parent_page:
                    # Вызываем асинхронно с задержкой 0 мс, чтобы дать Qt завершить сессию перетаскивания,
                    # предотвращая скрытие / пропажу строки из таблицы
                    QTimer.singleShot(0, lambda s=source_row, d=dest_row: self.parent_page.move_coord_row(s, d))
                    
        event.setDropAction(Qt.DropAction.IgnoreAction)
        event.accept()

    def paintEvent(self, event):
        super().paintEvent(event)
        
        if self.current_drop_row is not None and 0 <= self.current_drop_row <= self.rowCount():
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            default_h = self.verticalHeader().defaultSectionSize()
            
            # Вычисляем координату Y для линии вставки
            if self.current_drop_row == self.rowCount():
                y = 0
                for r in range(self.rowCount()):
                    y += self.rowHeight(r)
            else:
                y = 0
                for r in range(self.current_drop_row):
                    y += self.rowHeight(r)
                    
            gap = 0
            if self.current_drop_row < self.rowCount():
                current_height = self.rowHeight(self.current_drop_row)
                if current_height > default_h:
                    gap = (current_height - default_h) // 2
                    
            line_y = y + gap
            
            # Рисуем красивую неоновую линию (фиолетовый цвет Catppuccin Lavender)
            glow_color = QColor("#cba6f7")
            
            # Внешнее неоновое свечение
            pen_glow = QPen(QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 70), 6)
            painter.setPen(pen_glow)
            painter.drawLine(10, line_y, self.width() - 10, line_y)
            
            # Центральная линия
            pen_line = QPen(QColor("#b4befe"), 2)
            painter.setPen(pen_line)
            painter.drawLine(10, line_y, self.width() - 10, line_y)
            
            # Стилизованные крайние точки
            painter.setBrush(QBrush(QColor("#b4befe")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPoint(10, line_y), 5, 5)
            painter.drawEllipse(QPoint(self.width() - 10, line_y), 5, 5)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection()
        elif event.matches(QKeySequence.StandardKey.Paste):
            self.paste_selection()
        else:
            super().keyPressEvent(event)

    def copy_selection(self):
        items = self.selectedItems()
        if not items: return
        # Копируем текст первой выбранной ячейки
        QApplication.clipboard().setText(items[0].text())

    def paste_selection(self):
        items = self.selectedItems()
        if not items: return
        item = items[0]
        
        text = QApplication.clipboard().text().strip()
        if not text: return
        
        if item.column() == 1: # Колонка координат
            nums = re.findall(r'\d+', text)
            if len(nums) >= 2:
                item.setText(f"X: {nums[0]}, Y: {nums[1]}")
                wrapper = self.cellWidget(item.row(), 1)
                coord_widget = get_inner_widget(wrapper)
                if isinstance(coord_widget, CoordCellWidget):
                    coord_widget.set_values(int(nums[0]), int(nums[1]))
        elif item.column() == 0: # Колонка названия
            item.setText(text)

class TestMoveThread(QThread):
    finished = Signal()
    error_occurred = Signal(str)

    def __init__(self, target_pos, joy_settings, region, scale, marker_path, threshold, centering_enabled, centering_offset, scan_interval_ms, target_tolerance, map_path, wall_offset, wp_straight=4.0, wp_turn=1.8, early_stop=0.0, save_debug_map=False, passive_mode=False, lookahead_straight=5.5, lookahead_turn_min=1.5, stop_turn_pause=150):
        super().__init__()
        self.target_pos = target_pos # (x, y)
        self.joy_settings = joy_settings # {x, y, radius}
        self.region = region # {top, left, width, height}
        self.scale = scale
        self.marker_path = marker_path
        self.threshold = threshold
        self.centering_enabled = centering_enabled
        self.centering_offset = centering_offset
        self.scan_interval = scan_interval_ms / 1000.0
        self.target_tolerance = target_tolerance
        self.map_path = map_path
        self.wall_offset = wall_offset
        self.wp_straight = wp_straight
        self.wp_turn = wp_turn
        self.early_stop = early_stop
        self.save_debug_map = save_debug_map or passive_mode
        self.passive_mode = passive_mode
        self.lookahead_straight = lookahead_straight
        self.lookahead_turn_min = lookahead_turn_min
        self.stop_turn_pause = stop_turn_pause / 1000.0
        self.visited_path = []
        self.planned_path = []
        self.smooth_x = None
        self.smooth_y = None

    def run(self):
        try:
            print(f"DEBUG: Поток движения запущен. Цель: {self.target_pos}, Интервал: {self.scan_interval}с")
            
            # 1. Инициализация навигатора
            try:
                finder = PathFinder(self.map_path, self.wall_offset)
            except Exception as e:
                print(f"DEBUG: Ошибка навигатора: {e}")
                self.error_occurred.emit(f"Ошибка навигатора: {e}")
                return

            # Даем окну бота время полностью скрыться
            time.sleep(1.5)
            
            # 2. Активация окна (клик в центр джойстика)
            # ВАЖНО: Поскольку процесс DPI-aware, pyautogui (низкоуровневый API) требует физических координат.
            log_joy_x = int(self.joy_settings['x'])
            log_joy_y = int(self.joy_settings['y'])
            phys_joy_x = int(log_joy_x * self.scale)
            phys_joy_y = int(log_joy_y * self.scale)

            if not self.passive_mode:
                print(f"DEBUG NAV: Clicking joystick at physical ({phys_joy_x}, {phys_joy_y}) (logical: {log_joy_x}, {log_joy_y})")
                pyautogui.click(phys_joy_x, phys_joy_y)
                time.sleep(0.8)

            # Загружаем маркер
            mark_img_full = cv2.imread(self.marker_path, cv2.IMREAD_UNCHANGED)
            if mark_img_full is None: 
                self.error_occurred.emit("Не удалось загрузить маркер (mark.png)")
                return

            # Проверяем наличие альфа-канала (3 измерения в shape, 4-й канал в 3-м измерении)
            if len(mark_img_full.shape) == 3 and mark_img_full.shape[2] == 4:
                template = cv2.cvtColor(mark_img_full, cv2.COLOR_BGRA2BGR).astype(np.uint8)
            else:
                template = cv2.imread(self.marker_path, cv2.IMREAD_COLOR)
            mask = None

            marker_h, marker_w = template.shape[:2]
            
            # 3. Цикл движения по маршруту
            start_time = time.time()
            max_duration = 30.0

            print("DEBUG NAV: Starting movement loop...")
            if not self.passive_mode:
                pyautogui.mouseDown(phys_joy_x, phys_joy_y)

            path = []
            path_index = 0

            with mss.mss() as sct:
                phys_region = {
                    "top": int(self.region["top"] * self.scale),
                    "left": int(self.region["left"] * self.scale),
                    "width": int(self.region["width"] * self.scale),
                    "height": int(self.region["height"] * self.scale)
                }

                while time.time() - start_time < max_duration:
                    if not self.isRunning(): break

                    sct_img = sct.grab(phys_region)
                    img_np = np.array(sct_img, dtype=np.uint8)
                    img_rgb = cv2.cvtColor(img_np, cv2.COLOR_BGRA2BGR).astype(np.uint8)

                    if mask is not None:
                        res = cv2.matchTemplate(img_rgb, template, cv2.TM_CCOEFF_NORMED, mask=mask)
                    else:
                        res = cv2.matchTemplate(img_rgb, template, cv2.TM_CCOEFF_NORMED)

                    _, max_val, _, max_loc = cv2.minMaxLoc(res)

                    if max_val >= self.threshold:
                            # Определяем координаты цели для динамического сглаживания
                        raw_target_rel_x = 0
                        raw_target_rel_y = 0
                        if self.target_pos is not None:
                            if self.target_pos[0] > self.region["width"]:
                                raw_target_rel_x = self.target_pos[0] - self.region["left"]
                                raw_target_rel_y = self.target_pos[1] - self.region["top"]
                            else:
                                raw_target_rel_x = self.target_pos[0]
                                raw_target_rel_y = self.target_pos[1]
                        
                        raw_rel_x = max_loc[0] / self.scale + (marker_w / self.scale) / 2
                        raw_rel_y = max_loc[1] / self.scale + (marker_h / self.scale) / 2
                        if self.centering_enabled:
                            raw_rel_x = max_loc[0] / self.scale + self.centering_offset[0] / self.scale
                            raw_rel_y = max_loc[1] / self.scale + self.centering_offset[1] / self.scale
                        
                        raw_final_dist = math.sqrt((raw_target_rel_x - raw_rel_x)**2 + (raw_target_rel_y - raw_rel_y)**2) if self.target_pos else 999.0

                        # Определяем, является ли предстоящий поворот крутым для динамического сглаживания
                        is_sharp_turn = False
                        wp_dist = 999.0
                        if path and path_index < len(path):
                            waypoint = path[path_index]
                            wp_dist = math.hypot(waypoint[0] - raw_rel_x, waypoint[1] - raw_rel_y)
                            if path_index < len(path) - 1:
                                if path_index > 0:
                                    prev_wp = path[path_index-1]
                                    curr_dx = waypoint[0] - prev_wp[0]
                                    curr_dy = waypoint[1] - prev_wp[1]
                                else:
                                    curr_dx = waypoint[0] - raw_rel_x
                                    curr_dy = waypoint[1] - raw_rel_y
                                next_dx = path[path_index+1][0] - waypoint[0]
                                next_dy = path[path_index+1][1] - waypoint[1]
                                curr_len = math.hypot(curr_dx, curr_dy)
                                next_len = math.hypot(next_dx, next_dy)
                                if curr_len > 0.1 and next_len > 0.1:
                                    dot_product = (curr_dx * next_dx + curr_dy * next_dy) / (curr_len * next_len)
                                    if dot_product < 0.7:  # cos(45°) ≈ 0.707
                                        is_sharp_turn = True

                        # Применяем фильтр экспоненциального сглаживания (EMA) для устранения микро-джиттера (шума)
                        alpha = 1.0
                        if self.smooth_x is None:
                            self.smooth_x = raw_rel_x
                            self.smooth_y = raw_rel_y
                        else:
                            # Динамический коэффициент сглаживания (alpha): снижаем сглаживание (альфа к 1.0) при приближении к финишу или поворотам
                            alpha = 0.5
                            if raw_final_dist < 15.0:
                                # Плавный переход от 0.5 (на 15px) до 1.0 (на финише) для полной ликвидации лага координат
                                alpha = 1.0 - (raw_final_dist / 15.0) * 0.5
                            elif is_sharp_turn and wp_dist < 10.0:
                                # Снижаем задержку координат при приближении к резким углам
                                alpha = 1.0 - (wp_dist / 10.0) * 0.5
                                
                            alpha = max(0.5, min(1.0, alpha))
                            self.smooth_x = alpha * raw_rel_x + (1 - alpha) * self.smooth_x
                            self.smooth_y = alpha * raw_rel_y + (1 - alpha) * self.smooth_y

                        rel_x = self.smooth_x
                        rel_y = self.smooth_y

                        print(f"DEBUG NAV: Character at RegionLog({int(rel_x)}, {int(rel_y)}) (alpha: {alpha:.2f})")
                        self.visited_path.append((rel_x, rel_y))

                        # Если цель не задана (в ручном пассивном режиме), то пропускаем навигацию
                        if self.target_pos is None:
                            time.sleep(self.scan_interval)
                            continue

                        # Определяем цель
                        target_rel_x = raw_target_rel_x
                        target_rel_y = raw_target_rel_y

                        print(f"DEBUG NAV: Target logical relative: ({int(target_rel_x)}, {int(target_rel_y)})")

                        if not path:
                            print(f"DEBUG NAV: Planning path from ({int(rel_x)}, {int(rel_y)}) to ({int(target_rel_x)}, {int(target_rel_y)})")
                            path = finder.get_path((rel_x, rel_y), (target_rel_x, target_rel_y))
                            self.planned_path = path
                            if not path:
                                print(f"DEBUG NAV: Path planning returned None or Empty! Stopping thread with navigation error.")
                                self.error_occurred.emit("Путь не найден! Убедитесь, что вы и цель стоите на белых маршрутах.")
                                break
                            print(f"DEBUG NAV: Path planned successfully. Waypoints: {path}")
                            path_index = 0
                            self.min_final_dist = 999.0

                        # Проверяем расстояние до финальной цели с учетом эффективной минимальной погрешности и ранней остановки
                        effective_tolerance = max(0.0, self.target_tolerance)
                        final_dist = math.sqrt((target_rel_x - rel_x)**2 + (target_rel_y - rel_y)**2)
                        
                        if not hasattr(self, 'min_final_dist'):
                            self.min_final_dist = 999.0
                        if final_dist < self.min_final_dist:
                            self.min_final_dist = final_dist
                        
                        if final_dist <= max(effective_tolerance, self.early_stop):
                            print(f"DEBUG NAV: Distance {final_dist:.2f} <= early stop threshold {max(effective_tolerance, self.early_stop)}. Arrived! Breaking movement loop.")
                            break
                            
                        # Если мы перелетели цель (расстояние начало увеличиваться после сближения)
                        if self.min_final_dist < 3.0 and final_dist > self.min_final_dist + 0.5:
                            print(f"DEBUG NAV: Overshot target (min was {self.min_final_dist:.2f}, now {final_dist:.2f}). Arrived! Breaking movement loop.")
                            break

                        if path_index < len(path):
                            waypoint = path[path_index]
                            
                            # Для крутых поворотов требуем подойти вплотную, чтобы не срезать угол по диагонали прямо в стену.
                            current_wp_tolerance = self.wp_turn if is_sharp_turn else self.wp_straight

                            # Проекционный контроль прохождения вейпоинта (Dot Product Check)
                            has_passed_waypoint = False
                            if path_index < len(path) - 1:
                                prev_wp = path[path_index-1] if path_index > 0 else (rel_x, rel_y)
                                seg_dx = waypoint[0] - prev_wp[0]
                                seg_dy = waypoint[1] - prev_wp[1]
                                char_dx = rel_x - waypoint[0]
                                char_dy = rel_y - waypoint[1]
                                # Если dot > 0, персонаж пересек плоскость вейпоинта
                                if (seg_dx * char_dx + seg_dy * char_dy) > 0:
                                    has_passed_waypoint = True

                            # Строгий контроль углов: на крутых поворотах игнорируем проекционный срез плоскости
                            if is_sharp_turn:
                                can_switch = wp_dist < current_wp_tolerance
                            else:
                                can_switch = wp_dist < current_wp_tolerance or has_passed_waypoint

                            if can_switch and path_index < len(path) - 1:
                                # Микро-остановка перед поворотом (Stop-and-Turn)
                                if is_sharp_turn and not self.passive_mode and self.stop_turn_pause > 0.0:
                                    print(f"DEBUG NAV: Sharp turn waypoint reached! Stopping character for {int(self.stop_turn_pause*1000)}ms to eliminate drift...")
                                    pyautogui.mouseUp()
                                    time.sleep(self.stop_turn_pause)
                                    # Заново зажимаем джойстик в центре
                                    pyautogui.mouseDown(phys_joy_x, phys_joy_y)

                                path_index += 1
                                waypoint = path[path_index]
                                wp_dist = math.sqrt((waypoint[0] - rel_x)**2 + (waypoint[1] - rel_y)**2)
                                print(f"DEBUG NAV: Waypoint reached. Switching to next waypoint index {path_index} at logical relative {waypoint} (dist: {wp_dist:.2f} px, sharp_turn: {is_sharp_turn}, passed: {has_passed_waypoint})")

                            # --- Алгоритм "Виртуальная Морковка" (Pure Pursuit) ---
                            # Динамическая дистанция взгляда вперед (в логических пикселях).
                            if is_sharp_turn:
                                # На крутых поворотах сжимаем морковку по мере приближения к углу (от 4.0 до min_lookahead)
                                lookahead = max(self.lookahead_turn_min, min(4.0, wp_dist))
                            else:
                                # На прямых участках держим морковку дальше для плавности
                                lookahead = self.lookahead_straight
                            
                            carrot_x = waypoint[0]
                            carrot_y = waypoint[1]
                            
                            # Если мы еще не достигли финальной точки, рассчитываем морковку вдоль пути
                            if path_index < len(path) - 1:
                                remaining_lookahead = lookahead
                                curr_pt = (rel_x, rel_y)
                                
                                # Расстояние до ближайшего целевого вейпоинта
                                dist_to_wp = math.hypot(waypoint[0] - rel_x, waypoint[1] - rel_y)
                                
                                if dist_to_wp >= remaining_lookahead:
                                    # Морковка лежит на отрезке между персонажем и текущим вейпоинтом
                                    if dist_to_wp > 0.1:
                                        ux = (waypoint[0] - rel_x) / dist_to_wp
                                        uy = (waypoint[1] - rel_y) / dist_to_wp
                                        carrot_x = rel_x + ux * remaining_lookahead
                                        carrot_y = rel_y + uy * remaining_lookahead
                                else:
                                    # Морковка "сворачивает за угол" на следующие сегменты
                                    remaining_lookahead -= dist_to_wp
                                    curr_pt = waypoint
                                    
                                    # Идем по оставшимся сегментам пути
                                    for i in range(path_index, len(path) - 1):
                                        next_pt = path[i+1]
                                        seg_dx = next_pt[0] - curr_pt[0]
                                        seg_dy = next_pt[1] - curr_pt[1]
                                        seg_len = math.hypot(seg_dx, seg_dy)
                                        
                                        if remaining_lookahead <= seg_len:
                                            # Морковка лежит на этом сегменте
                                            if seg_len > 0.1:
                                                ux = seg_dx / seg_len
                                                uy = seg_dy / seg_len
                                                carrot_x = curr_pt[0] + ux * remaining_lookahead
                                                carrot_y = curr_pt[1] + uy * remaining_lookahead
                                            remaining_lookahead = 0
                                            break
                                        else:
                                            # Морковка лежит еще дальше
                                            remaining_lookahead -= seg_len
                                            curr_pt = next_pt
                                            
                                    # Если мы исчерпали путь, а lookahead остался, морковка — это финальная точка
                                    if remaining_lookahead > 0:
                                        carrot_x = path[-1][0]
                                        carrot_y = path[-1][1]
                                        
                            dx = carrot_x - rel_x
                            dy = carrot_y - rel_y

                            angle = math.atan2(dy, dx)

                            # Тянем джойстик на полную мощность, так как в игре нет регулируемой скорости (только 0% или 100%)
                            if not self.passive_mode:
                                phys_radius = self.joy_settings['radius'] * self.scale
                                
                                drag_x_phys = phys_joy_x + math.cos(angle) * phys_radius
                                drag_y_phys = phys_joy_y + math.sin(angle) * phys_radius

                                print(f"DEBUG NAV: Dragging joystick to physical: ({int(drag_x_phys)}, {int(drag_y_phys)}) [angle: {math.degrees(angle):.1f}°]")
                                pyautogui.moveTo(int(drag_x_phys), int(drag_y_phys), duration=0.05)
                    time.sleep(self.scan_interval)

            if not self.passive_mode:
                pyautogui.mouseUp()
            print("DEBUG: Поток движения завершен штатно")
            
        except Exception as e:
            print(f"Ошибка в потоке движения: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.save_debug_image()
            self.finished.emit()

    def save_debug_image(self):
        if not self.save_debug_map or len(self.visited_path) == 0:
            return
        try:
            # Загружаем и вырезаем регион
            with open(self.map_path, "rb") as f:
                chunk = np.frombuffer(f.read(), dtype=np.uint8)
                full_img = cv2.imdecode(chunk, cv2.IMREAD_GRAYSCALE)
            
            if full_img is not None:
                # Конвертируем ч/б карту в BGR, чтобы рисовать цветом
                img_bgr = cv2.cvtColor(full_img, cv2.COLOR_GRAY2BGR)
                
                # Вычисляем регион выреза так же, как в PathFinder
                region_info = None
                map_dir = os.path.dirname(self.map_path)
                region_info_path = os.path.join(map_dir, "region.json")
                if os.path.exists(region_info_path):
                    with open(region_info_path, "r") as f:
                        region_info = json.load(f)
                
                if region_info:
                    scale = region_info.get("scale", self.scale)
                    px = int(region_info["x"] * scale)
                    py = int(region_info["y"] * scale)
                    pw = int(region_info["w"] * scale)
                    ph = int(region_info["h"] * scale)
                    y2, x2 = min(img_bgr.shape[0], py+ph), min(img_bgr.shape[1], px+pw)
                    cropped_bgr = img_bgr[py:y2, px:x2].copy()
                else:
                    cropped_bgr = img_bgr.copy()
                    scale = self.scale
                
                # Рисуем запланированный путь (синим цветом: (255, 0, 0))
                if hasattr(self, 'planned_path') and self.planned_path:
                    for idx in range(len(self.planned_path) - 1):
                        pt1 = (int(self.planned_path[idx][0] * scale), int(self.planned_path[idx][1] * scale))
                        pt2 = (int(self.planned_path[idx+1][0] * scale), int(self.planned_path[idx+1][1] * scale))
                        cv2.line(cropped_bgr, pt1, pt2, (255, 0, 0), 1)
                
                # Рисуем фактический маршрут героя (красным цветом: (0, 0, 255))
                for idx in range(len(self.visited_path) - 1):
                    pt1 = (int(self.visited_path[idx][0] * scale), int(self.visited_path[idx][1] * scale))
                    pt2 = (int(self.visited_path[idx+1][0] * scale), int(self.visited_path[idx+1][1] * scale))
                    cv2.line(cropped_bgr, pt1, pt2, (0, 0, 255), 1)
                    
                # Рисуем точки вейпоинтов (зеленым: (0, 255, 0))
                if hasattr(self, 'planned_path') and self.planned_path:
                    for pt in self.planned_path:
                        cv2.circle(cropped_bgr, (int(pt[0] * scale), int(pt[1] * scale)), 1, (0, 255, 0), -1)

                # Сохраняем в ассеты
                debug_img_path = os.path.join(os.path.dirname(self.marker_path), "debug_test_run.png")
                cv2.imwrite(debug_img_path, cropped_bgr)
                print(f"DEBUG NAV: Saved debug map to {debug_img_path}")
        except Exception as ex:
            print(f"DEBUG: Не удалось сохранить отладочную карту: {ex}")

class AutoDetector(QThread):
    finished = Signal(object) # Передает (x, y) или None

    def __init__(self, region_str, mark_path, threshold, timeout_sec, centering_enabled, centering_offset, screenshot_path=None):
        super().__init__()
        self.region_str = region_str
        self.mark_path = mark_path
        self.threshold = threshold
        self.timeout_sec = timeout_sec
        self.centering_enabled = centering_enabled
        self.centering_offset = centering_offset # (dx, dy)
        self.screenshot_path = screenshot_path

    def run(self):
        try:
            print(f"DEBUG: AutoDetector.run() entered. Thread ID: {int(QThread.currentThreadId())}")
            
            # Даем время окну бота точно свернуться
            time.sleep(1.0)
            
            if not os.path.exists(self.mark_path):
                self.finished.emit(None)
                return

            mark_img_full = cv2.imread(self.mark_path, cv2.IMREAD_UNCHANGED)
            if mark_img_full is None:
                self.finished.emit(None)
                return

            if len(mark_img_full.shape) == 3 and mark_img_full.shape[2] == 4:
                template = cv2.cvtColor(mark_img_full, cv2.COLOR_BGRA2BGR)
            else:
                template = cv2.imread(self.mark_path, cv2.IMREAD_COLOR)
            mask = None

            try:
                x_reg, y_reg, w_reg, h_reg = map(int, self.region_str.split(","))
            except Exception:
                self.finished.emit(None)
                return

            screen = QApplication.primaryScreen()
            scale = screen.devicePixelRatio() if screen else 1.0

            phys_region = {
                "top": int(y_reg * scale),
                "left": int(x_reg * scale),
                "width": int(w_reg * scale),
                "height": int(h_reg * scale)
            }

            start_time = time.time()
            found_pos = None

            with mss.mss() as sct:
                while time.time() - start_time < self.timeout_sec:
                    try:
                        sct_img = sct.grab(phys_region)
                        img = np.array(sct_img, dtype=np.uint8)
                        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

                        if mask is not None:
                            res = cv2.matchTemplate(img_rgb, template, cv2.TM_CCOEFF_NORMED, mask=mask)
                        else:
                            res = cv2.matchTemplate(img_rgb, template, cv2.TM_CCOEFF_NORMED)

                        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)                            
                        if max_val >= self.threshold:
                            # Маркер найден! Сделаем скриншот всего экрана, если путь указан
                            if self.screenshot_path:
                                full_sct = sct.grab(sct.monitors[0]) # Весь экран
                                mss.tools.to_png(full_sct.rgb, full_sct.size, output=self.screenshot_path)

                            # Координаты левого верхнего угла найденного маркера на экране (логические)
                            found_x = x_reg + max_loc[0] / scale
                            found_y = y_reg + max_loc[1] / scale
                            
                            if self.centering_enabled:
                                # Добавляем смещение центра относительно левого верхнего угла (в логических пикселях, соответствующих MapRecorder)
                                final_x = int(found_x + self.centering_offset[0] / scale)
                                final_y = int(found_y + self.centering_offset[1] / scale)
                            else:
                                # Если центрирование выключено, используем центр самого маркера
                                marker_h, marker_w = template.shape[:2]
                                final_x = int(found_x + (marker_w / scale) / 2)
                                final_y = int(found_y + (marker_h / scale) / 2)
                            
                            found_pos = (final_x, final_y)
                            break
                    except Exception:
                        pass
                    time.sleep(0.2)
            
            self.finished.emit(found_pos)
            
        except Exception:
            self.finished.emit(None)

class InteractiveMapWidget(QWidget):
    coordinate_changed = pyqtSignal(int, int)

    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.scale_factor = 5 # Увеличиваем масштаб в 5 раз для удобства клика
        self.settings_obj = QSettings("XPHero", "BotSettings")
        
        self.image_path = image_path
        self.mode = "center" # "center" или "erase"
        self.eraser_size = 1
        self.img_data = None # Оригинальные RGBA данные
        self.setMouseTracking(True) # Нужно для mouseMoveEvent при удержании ЛКМ
        self.load_image()

    def load_image(self):
        # Загружаем через OpenCV чтобы гарантированно получить альфа-канал
        img = cv2.imread(self.image_path, cv2.IMREAD_UNCHANGED)
        if img is not None:
            if len(img.shape) == 3 and img.shape[2] == 4:
                self.img_data = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
            elif len(img.shape) == 3 and img.shape[2] == 3:
                self.img_data = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA)
            elif len(img.shape) == 2:
                self.img_data = cv2.cvtColor(img, cv2.COLOR_GRAY2RGBA)
        else:
            self.img_data = np.zeros((20, 20, 4), dtype=np.uint8)
            self.img_data[:,:,3] = 255 # Непрозрачный фон
            
        self._rebuild_pixmap()
        
        # Загружаем сохраненные координаты только при полной загрузке нового изображения
        h, w = self.img_data.shape[:2]
        self.original_x = self.settings_obj.value("centering_x", w // 2, type=int)
        self.original_y = self.settings_obj.value("centering_y", h // 2, type=int)
        
    def _rebuild_pixmap(self):
        if self.img_data is None: return
        
        mask_color_hex = self.settings_obj.value("mask_color", "#00ff00", type=str)
        mask_qcolor = QColor(mask_color_hex)
        
        h, w = self.img_data.shape[:2]
        display_img = self.img_data.copy()
        
        # Находим пиксели, где альфа < 128
        mask = display_img[:, :, 3] < 128
        
        # Заменяем цвет этих пикселей на mask_color для визуализации
        display_img[mask] = [mask_qcolor.red(), mask_qcolor.green(), mask_qcolor.blue(), 255]
        
        # Конвертируем в QPixmap через bytes чтобы избежать проблем с памятью
        bytes_per_line = 4 * w
        self._q_data = bytes(display_img.data)
        q_img = QImage(self._q_data, w, h, bytes_per_line, QImage.Format.Format_RGBA8888)
        original_pixmap = QPixmap.fromImage(q_img)
        
        # Увеличиваем картинку без размытия (FastTransformation)
        self.pixmap = original_pixmap.scaled(
            w * self.scale_factor, 
            h * self.scale_factor, 
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.FastTransformation
        )
            
        self.setFixedSize(self.pixmap.size())
        self.update()
        
    def save_mask(self):
        if self.img_data is not None:
            # Конвертируем обратно в BGRA для сохранения через OpenCV
            save_img = cv2.cvtColor(self.img_data, cv2.COLOR_RGBA2BGRA)
            cv2.imwrite(self.image_path, save_img)
            return True
        return False
        
    def reset_mask(self):
        self.load_image()

    def auto_crop(self):
        if self.img_data is None: return
        
        # Находим координаты непрозрачных пикселей (альфа > 0)
        alpha = self.img_data[:, :, 3]
        # Используем numpy для поиска границ непрозрачной области
        non_zero = np.where(alpha > 0)
        if len(non_zero[0]) == 0: return
        
        top, bottom = np.min(non_zero[0]), np.max(non_zero[0])
        left, right = np.min(non_zero[1]), np.max(non_zero[1])
        
        # Обрезаем данные
        self.img_data = self.img_data[top:bottom+1, left:right+1].copy()
        
        # Сохраняем результат
        self.save_mask()
        
        # Пересчитываем координаты прицела относительно новой обрезки
        self.original_x = max(0, self.original_x - left)
        self.original_y = max(0, self.original_y - top)
        self.settings_obj.setValue("centering_x", self.original_x)
        self.settings_obj.setValue("centering_y", self.original_y)
        
        # Перерисовываем виджет
        self._rebuild_pixmap()
        return True

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.pixmap)
        
        # Настраиваем перо для прицела
        pen = QPen(QColor("black"))
        pen.setWidth(2)
        painter.setPen(pen)
        
        # Переводим оригинальные координаты в координаты увеличенной картинки
        draw_x = self.original_x * self.scale_factor + (self.scale_factor // 2)
        draw_y = self.original_y * self.scale_factor + (self.scale_factor // 2)
        
        # Рисуем вертикальную и горизонтальную линии
        painter.drawLine(draw_x, 0, draw_x, self.height())
        painter.drawLine(0, draw_y, self.width(), draw_y)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.mode == "center":
                # Получаем координаты клика на увеличенной картинке
                click_x = max(0, min(int(event.position().x()), self.width() - 1))
                click_y = max(0, min(int(event.position().y()), self.height() - 1))
                
                # Переводим обратно в оригинальные координаты
                self.original_x = click_x // self.scale_factor
                self.original_y = click_y // self.scale_factor
                
                self.update()
                
                self.settings_obj.setValue("centering_x", self.original_x)
                self.settings_obj.setValue("centering_y", self.original_y)
                
                self.coordinate_changed.emit(self.original_x, self.original_y)
            elif self.mode == "erase":
                self._apply_eraser(event.position())

    def mouseMoveEvent(self, event):
        if self.mode == "erase" and (event.buttons() & Qt.MouseButton.LeftButton):
            self._apply_eraser(event.position())
            
    def _apply_eraser(self, pos):
        if self.img_data is None: return
        
        h, w = self.img_data.shape[:2]
        
        # Переводим в координаты оригинала
        center_x = int(pos.x() / self.scale_factor)
        center_y = int(pos.y() / self.scale_factor)
        
        size = max(1, self.eraser_size)
        half = size // 2
        
        # Для size=1: half=0, x_start=center_x, x_end=center_x+1
        x_start = max(0, center_x - half)
        y_start = max(0, center_y - half)
        x_end = min(w, center_x - half + size)
        y_end = min(h, center_y - half + size)
        
        if x_start >= x_end or y_start >= y_end: return
        
        # Устанавливаем альфа-канал в 0 (прозрачность)
        self.img_data[y_start:y_end, x_start:x_end, 3] = 0
        
        # Перерисовываем
        self._rebuild_pixmap()

    def reset_to_center(self):
        orig_w = self.pixmap.width() // self.scale_factor
        orig_h = self.pixmap.height() // self.scale_factor
        self.original_x = orig_w // 2
        self.original_y = orig_h // 2
        self.settings_obj.setValue("centering_x", self.original_x)
        self.settings_obj.setValue("centering_y", self.original_y)
        self.update()
        self.coordinate_changed.emit(self.original_x, self.original_y)

class SettingsPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window # Ссылка на главное окно для возврата
        
        self.settings_obj = QSettings("XPHero", "BotSettings")
        self.current_coords_tab = "buttons" # По умолчанию
        self.map_recorder = MapRecorder(self.settings_obj)
        self.map_recorder.preview_updated.connect(self.on_map_preview_updated)
        self.map_recorder.preview_image_updated.connect(self.on_map_preview_image_updated)
        
        # Инициализируем глобальный поток отслеживания хоткея экстренной остановки
        self.hotkey_thread = GlobalHotkeyThread(self)
        self.hotkey_thread.hotkey_triggered.connect(self.emergency_stop)
        self.hotkey_thread.start()
        
        # Миграция из Сундуков в Подарки (один раз)
        if not self.settings_obj.value("migrated_chests_to_gifts_v1", False, type=bool):
            self.migrate_chests_to_gifts()
            self.settings_obj.setValue("migrated_chests_to_gifts_v1", True)

        # Миграция координат в подвкладку 3
        if not self.settings_obj.value("migrated_to_subtabs_v1", False, type=bool):
            self.migrate_to_subtabs()
            self.settings_obj.setValue("migrated_to_subtabs_v1", True)

        self.coords_subtabs_count = int(self.settings_obj.value("coords_subtabs_count", 3))
        self.current_subtab_index = int(self.settings_obj.value("current_subtab_index", 3))
        if self.current_subtab_index > self.coords_subtabs_count:
            self.current_subtab_index = self.coords_subtabs_count

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)

        # Верхняя панель
        top_bar = QHBoxLayout()
        
        self.back_btn = QPushButton("⬅ Назад")
        self.back_btn.setStyleSheet("background-color: #313244; color: white; border-radius: 4px; padding: 8px 16px; font-weight: bold;")
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.clicked.connect(self.go_back)
        
        title = QLabel("Настройки")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        
        # Настройки перекрестья
        self.crosshair_color_btn = QPushButton()
        self.crosshair_color_btn.setFixedSize(32, 32)
        color_hex = self.settings_obj.value("test_crosshair_color", "#ff0000", type=str)
        self.crosshair_color_btn.setStyleSheet(f"background-color: {color_hex}; border-radius: 4px; border: 2px solid #313244;")
        self.crosshair_color_btn.clicked.connect(self.pick_crosshair_color)
        
        self.crosshair_len_spin = QSpinBox()
        self.crosshair_len_spin.setRange(0, 100)
        self.crosshair_len_spin.setValue(self.settings_obj.value("test_crosshair_length", 15, type=int))
        self.crosshair_len_spin.setFixedWidth(50)
        self.crosshair_len_spin.setStyleSheet("background-color: #313244; color: #cdd6f4; padding: 4px;")
        self.crosshair_len_spin.valueChanged.connect(self.on_crosshair_settings_changed)
        
        # Кнопка Тест
        self.test_btn = QPushButton("Тест")
        self.test_btn.setCheckable(True)
        self.test_btn.setStyleSheet("""
            QPushButton {
                background-color: #f38ba8; 
                color: #11111b; 
                border-radius: 4px; 
                padding: 8px 16px; 
                font-weight: bold;
            }
            QPushButton:checked {
                background-color: #a6e3a1;
            }
        """)
        self.test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.test_overlay = None
        self.test_btn.toggled.connect(self.toggle_test_overlay)
        
        top_bar.addWidget(self.back_btn)
        top_bar.addSpacing(20)
        top_bar.addWidget(title)
        
        # Группируем настройки теста в один компактный блок
        test_controls = QHBoxLayout()
        test_controls.setSpacing(5)
        
        test_label = QLabel("Тест:")
        test_label.setStyleSheet("color: #94e2d5; font-weight: bold; margin-left: 20px;")
        
        test_controls.addWidget(test_label)
        test_controls.addWidget(self.crosshair_color_btn)
        test_controls.addWidget(self.crosshair_len_spin)
        test_controls.addSpacing(10)
        test_controls.addWidget(self.test_btn)
        
        top_bar.addLayout(test_controls)
        top_bar.addStretch() # Теперь stretch в самом конце, чтобы прижать ВСЁ влево
        
        self.layout.addLayout(top_bar)

        # Сплиттер для бокового меню и контента
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.layout.addWidget(self.splitter, stretch=1)

        # Левое меню категорий
        self.category_list = QListWidget()
        self.category_list.setStyleSheet("""
            QListWidget {
                background-color: #181825; 
                border: 1px solid #313244; 
                border-radius: 8px; 
                font-size: 16px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 10px;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background-color: #cba6f7;
                color: #11111b;
                font-weight: bold;
            }
        """)
        self.splitter.addWidget(self.category_list)

        # Правая панель (контент)
        self.content_stack = QStackedWidget()
        self.splitter.addWidget(self.content_stack)
        
        self.splitter.setSizes([200, 800]) # Начальные пропорции

        self.setup_categories()
        self.category_list.currentRowChanged.connect(self.change_category)

    def migrate_chests_to_gifts(self):
        """Переносит все данные из вкладки 'Сундуки' во вкладку 'Подарки' один раз."""
        chests_json = self.settings_obj.value("coords_list_chests", "[]", type=str)
        gifts_json = self.settings_obj.value("coords_list_gifts", "[]", type=str)
        
        try:
            chests_list = json.loads(chests_json)
            gifts_list = json.loads(gifts_json)
            
            if chests_list:
                # Объединяем списки
                gifts_list.extend(chests_list)
                # Сохраняем обновленные подарки
                self.settings_obj.setValue("coords_list_gifts", json.dumps(gifts_list))
                # Очищаем сундуки (так как они переехали)
                self.settings_obj.setValue("coords_list_chests", "[]")
                print(f"DEBUG: Миграция завершена. {len(chests_list)} точек перенесено из Сундуков в Подарки.")
        except Exception as e:
            print(f"DEBUG: Ошибка миграции: {e}")

    def migrate_to_subtabs(self):
        """Переносит все данные из bosses, chests, gifts в формат с индексом 3 и переименовывает скриншоты."""
        tabs_to_migrate = ["bosses", "chests", "gifts"]
        for tab in tabs_to_migrate:
            old_key = f"coords_list_{tab}"
            if self.settings_obj.contains(old_key):
                new_key = f"coords_list_{tab}_3"
                
                # Переносим данные
                data = self.settings_obj.value(old_key)
                self.settings_obj.setValue(new_key, data)
                
                # Переименовываем скриншоты
                try:
                    coords = json.loads(data)
                    for item in coords:
                        name = item.get("name", "")
                        if name:
                            old_path = os.path.join(SCREENSHOTS_DIR, f"{tab}_{name}.png")
                            new_path = os.path.join(SCREENSHOTS_DIR, f"{tab}_3_{name}.png")
                            if os.path.exists(old_path) and not os.path.exists(new_path):
                                os.rename(old_path, new_path)
                                print(f"DEBUG: Renamed screenshot {old_path} -> {new_path}")
                except Exception as e:
                    print(f"DEBUG: Ошибка миграции скриншотов для {tab}: {e}")
                    
                self.settings_obj.remove(old_key)
                print(f"DEBUG: Миграция {tab} завершена в подвкладку 3.")

    def save_to_history(self):
        # Сохраняем глубокую копию текущего списка
        import copy
        self.history_stack.append(copy.deepcopy(self.coords_list))
        # Ограничим размер стека, чтобы не ел память (например, 20 шагов)
        if len(self.history_stack) > 20:
            self.history_stack.pop(0)
        self.undo_btn.setEnabled(True)

    def undo_last_action(self):
        if not self.history_stack:
            return
            
        # Достаем последнее состояние
        previous_state = self.history_stack.pop()
        self.coords_list = previous_state
        
        # Сохраняем в настройки
        key = f"coords_list_{self.current_coords_tab}"
        self.settings_obj.setValue(key, json.dumps(self.coords_list))
        
        # Перезагружаем таблицу из обновленного self.coords_list
        self.load_coords()
        
        if not self.history_stack:
            self.undo_btn.setEnabled(False)

    def setup_categories(self):
        # 1. Категория Центрирование
        item_centering = QListWidgetItem("Центрирование")
        self.category_list.addItem(item_centering)
        
        centering_page = QWidget()
        centering_layout = QVBoxLayout(centering_page)
        centering_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # Галочка "Включить центрирование"
        toggle_layout = QHBoxLayout()
        toggle_label = QLabel("Включить центрирование:")
        toggle_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.cb_enable_centering = QCheckBox()
        self.cb_enable_centering.setStyleSheet("QCheckBox::indicator { width: 20px; height: 20px; }")
        
        is_centering_enabled = self.settings_obj.value("centering_enabled", False, type=bool)
        self.cb_enable_centering.setChecked(is_centering_enabled)
        
        toggle_layout.addWidget(toggle_label)
        toggle_layout.addWidget(self.cb_enable_centering)
        toggle_layout.addStretch()
        centering_layout.addLayout(toggle_layout)
        
        # --- Секция: Определение маркера ---
        marker_layout = QHBoxLayout()
        
        # Слайдер уверенности
        thresh_val = self.settings_obj.value("match_threshold", "75", type=str)
        self.thresh_label = QLabel(f"Уверенность (Threshold): {thresh_val}%")
        self.thresh_slider = QSlider(Qt.Orientation.Horizontal)
        self.thresh_slider.setRange(50, 100)
        self.thresh_slider.setValue(int(thresh_val))
        self.thresh_slider.setFixedWidth(200)
        self.thresh_slider.valueChanged.connect(self.on_threshold_changed)
        
        # Кнопка выбора цвета маски
        self.mask_color_btn = QPushButton("Цвет маски")
        self.mask_color_btn.setStyleSheet(f"background-color: {self.settings_obj.value('mask_color', '#00ff00', type=str)}; color: black; font-weight: bold; border-radius: 4px; padding: 4px;")
        self.mask_color_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mask_color_btn.clicked.connect(self.choose_mask_color)
        
        # Тайм-аут поиска
        timeout_label = QLabel("Тайм-аут поиска (сек):")
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 30)
        self.timeout_spin.setValue(self.settings_obj.value("marker_timeout", 5, type=int))
        self.timeout_spin.valueChanged.connect(lambda v: self.settings_obj.setValue("marker_timeout", v))
        self.timeout_spin.setStyleSheet("color: #cdd6f4; background-color: #313244; padding: 2px;")
        
        # Кнопка поиска
        self.detect_marker_btn = QPushButton("Определение маркера")
        self.detect_marker_btn.setStyleSheet("background-color: #89b4fa; color: #11111b; font-weight: bold; padding: 6px;")
        self.detect_marker_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.detect_marker_btn.clicked.connect(self.start_marker_detection)
        
        marker_layout.addWidget(self.thresh_label)
        marker_layout.addWidget(self.thresh_slider)
        marker_layout.addSpacing(10)
        marker_layout.addWidget(self.mask_color_btn)
        marker_layout.addSpacing(20)
        marker_layout.addWidget(timeout_label)
        marker_layout.addWidget(self.timeout_spin)
        marker_layout.addSpacing(20)
        marker_layout.addWidget(self.detect_marker_btn)
        marker_layout.addStretch()
        
        centering_layout.addLayout(marker_layout)
        
        info_label = QLabel("Кликните по миникарте, чтобы указать фактический центр персонажа:")
        info_label.setStyleSheet("font-size: 16px; margin-top: 15px; margin-bottom: 5px;")
        centering_layout.addWidget(info_label)
        
        # --- Редактор маски (Ластик) ---
        editor_controls = QHBoxLayout()
        editor_controls.setContentsMargins(0, 0, 0, 10)
        
        self.mode_btn = QPushButton("Режим: Центрирование")
        self.mode_btn.setFixedWidth(200)
        self.mode_btn.setStyleSheet("background-color: #313244; color: #cdd6f4; font-weight: bold; padding: 6px; border: 1px solid #45475a;")
        self.mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode_btn.clicked.connect(self.toggle_editor_mode)
        
        eraser_label = QLabel("Размер ластика:")
        eraser_label.setStyleSheet("margin-left: 15px;")
        self.eraser_spin = QSpinBox()
        self.eraser_spin.setRange(1, 10)
        self.eraser_spin.setValue(1)
        self.eraser_spin.setFixedWidth(50)
        self.eraser_spin.setStyleSheet("background-color: #313244; color: #cdd6f4; padding: 2px;")
        self.eraser_spin.valueChanged.connect(self.on_eraser_size_changed)
        
        self.save_mask_btn = QPushButton("Сохранить маску")
        self.save_mask_btn.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-weight: bold; padding: 6px;")
        self.save_mask_btn.clicked.connect(self.save_marker_mask)
        self.save_mask_btn.hide() # Показываем только в режиме ластика
        
        self.reset_mask_btn = QPushButton("Сбросить изменения")
        self.reset_mask_btn.setStyleSheet("background-color: #f38ba8; color: #11111b; font-weight: bold; padding: 6px;")
        self.reset_mask_btn.clicked.connect(self.reset_marker_mask)
        self.reset_mask_btn.hide()
        
        editor_controls.addWidget(self.mode_btn)
        editor_controls.addWidget(eraser_label)
        editor_controls.addWidget(self.eraser_spin)
        editor_controls.addSpacing(20)
        editor_controls.addWidget(self.save_mask_btn)
        editor_controls.addWidget(self.reset_mask_btn)
        editor_controls.addStretch()
        
        centering_layout.addLayout(editor_controls)
        
        self.edit_warning = QLabel("⚠ Режим ЛАСТИКА: водите мышкой по картинке, чтобы стирать фон")
        self.edit_warning.setStyleSheet("color: #f38ba8; font-weight: bold; margin-bottom: 5px;")
        self.edit_warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit_warning.hide()
        centering_layout.addWidget(self.edit_warning)
        
        # Интерактивная карта
        map_path = os.path.join(ASSETS_DIR, "mark.png")
        self.interactive_map = InteractiveMapWidget(map_path)
        # Карта теперь всегда активна, чтобы можно было редактировать маску
        self.interactive_map.setEnabled(True) 
        
        # --- Настройки захвата ---
        capture_settings = QHBoxLayout()
        capture_settings.setContentsMargins(0, 0, 0, 5)
        
        self.capture_btn = QPushButton("📷 Захватить маркер с экрана")
        self.capture_btn.setStyleSheet("background-color: #fab387; color: #11111b; font-weight: bold; padding: 8px;")
        self.capture_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.capture_btn.clicked.connect(self.capture_marker_from_screen)
        
        size_label = QLabel("Размер захвата:")
        size_label.setStyleSheet("margin-left: 15px;")
        self.capture_size_spin = QSpinBox()
        self.capture_size_spin.setRange(20, 150)
        self.capture_size_spin.setValue(self.settings_obj.value("capture_size", 40, type=int))
        self.capture_size_spin.setFixedWidth(60)
        self.capture_size_spin.setStyleSheet("background-color: #313244; color: #cdd6f4; padding: 4px;")
        self.capture_size_spin.valueChanged.connect(lambda v: self.settings_obj.setValue("capture_size", v))
        
        self.auto_crop_btn = QPushButton("✨ Авто-обрезка краев")
        self.auto_crop_btn.setStyleSheet("background-color: #b4befe; color: #11111b; font-weight: bold; padding: 8px; margin-left: 15px;")
        self.auto_crop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.auto_crop_btn.clicked.connect(self.on_auto_crop_clicked)
        
        capture_settings.addWidget(self.capture_btn)
        capture_settings.addWidget(size_label)
        capture_settings.addWidget(self.capture_size_spin)
        capture_settings.addWidget(self.auto_crop_btn)
        capture_settings.addStretch()
        
        centering_layout.addLayout(capture_settings)
        
        # Центрируем карту
        map_layout = QHBoxLayout()
        map_layout.addStretch()
        map_layout.addWidget(self.interactive_map)
        map_layout.addStretch()
        centering_layout.addLayout(map_layout)
        
        # Лейблы для координат
        self.coords_label = QLabel(f"Координаты (смещение): X: {self.interactive_map.original_x}, Y: {self.interactive_map.original_y}")
        self.coords_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 10px; color: #a6e3a1;")
        self.coords_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.interactive_map.coordinate_changed.connect(
            lambda x, y: self.coords_label.setText(f"Координаты (смещение): X: {x}, Y: {y}")
        )
        
        centering_layout.addWidget(self.coords_label)
        centering_layout.addStretch()
        
        self.content_stack.addWidget(centering_page)
        
        # Логика переключения
        def on_toggle_centering(state):
            is_checked = state == Qt.CheckState.Checked.value
            self.settings_obj.setValue("centering_enabled", is_checked)
            self.interactive_map.setEnabled(is_checked)
            if not is_checked:
                self.interactive_map.reset_to_center()
            
        self.cb_enable_centering.stateChanged.connect(on_toggle_centering)

        # 2. Категория Координаты
        item_coords = QListWidgetItem("Координаты")
        self.category_list.addItem(item_coords)
        
        coords_page = QWidget()
        coords_layout = QVBoxLayout(coords_page)
        coords_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        coords_layout.setContentsMargins(15, 10, 15, 15)
        
        # --- Вкладки (Кнопки, Боссы, Сундуки) ---
        self.coords_tabs_layout = QHBoxLayout()
        self.coords_tabs_layout.setSpacing(8)
        self.coords_tabs_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.coords_tabs_group = QButtonGroup(self)
        self.coords_tab_buttons = []
        
        tabs_data = ["Кнопки", "Боссы", "Сундуки", "Подарки"]
        for i, name in enumerate(tabs_data):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedWidth(100)
            btn.setFixedHeight(32)
            
            # Базовый стиль вкладок
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #313244;
                    color: #cdd6f4;
                    border: none;
                    border-radius: 4px;
                    font-weight: bold;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #45475a;
                }
                QPushButton:checked {
                    background-color: #b4befe;
                    color: #11111b;
                }
            """)
            
            self.coords_tabs_group.addButton(btn, i)
            self.coords_tabs_layout.addWidget(btn)
            self.coords_tab_buttons.append(btn)
            
        # По умолчанию выбрана первая вкладка
        self.coords_tab_buttons[0].setChecked(True)
        self.coords_tabs_group.idClicked.connect(self.on_coords_tab_changed)
        
        coords_layout.addLayout(self.coords_tabs_layout)
        
        # --- Подвкладки (1, 2, 3...) ---
        self.subtabs_container = QWidget()
        sp = self.subtabs_container.sizePolicy()
        sp.setRetainSizeWhenHidden(True)
        self.subtabs_container.setSizePolicy(sp)
        
        self.subtabs_layout = QHBoxLayout(self.subtabs_container)
        self.subtabs_layout.setContentsMargins(0, 0, 0, 0)
        self.subtabs_layout.setSpacing(5)
        self.subtabs_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.subtabs_group = QButtonGroup(self)
        self.subtabs_group.idClicked.connect(self.on_subtab_clicked)
        
        self.update_subtabs_ui()
        coords_layout.addWidget(self.subtabs_container)
        self.subtabs_container.hide() # По умолчанию скрыта (т.к. выбраны Кнопки)
        
        coords_layout.addSpacing(10)
        
        header_layout = QHBoxLayout()
        
        self.undo_btn = QPushButton("Вернуть")
        self.undo_btn.setStyleSheet("""
            QPushButton {
                background-color: #fab387; 
                color: #11111b; 
                border-radius: 4px; 
                padding: 6px 16px; 
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:disabled {
                background-color: #45475a;
                color: #7f849c;
            }
            QPushButton:hover:enabled {
                background-color: #f9e2af;
            }
        """)
        self.undo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.undo_btn.setEnabled(False)
        self.undo_btn.clicked.connect(self.undo_last_action)

        self.add_row_btn = QPushButton("Добавить")
        self.add_row_btn.setStyleSheet("""
            QPushButton {
                background-color: #a6e3a1; 
                color: #11111b; 
                border-radius: 4px; 
                padding: 6px 16px; 
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #94e2d5;
            }
        """)
        self.add_row_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_row_btn.clicked.connect(self.add_coord_row)
        self.full_map_btn = QPushButton("Фулл карта")
        self.full_map_btn.setStyleSheet("""
            QPushButton {
                background-color: #cba6f7; 
                color: #11111b; 
                border-radius: 4px; 
                padding: 6px 16px; 
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #b4befe;
            }
        """)
        self.full_map_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.full_map_btn.clicked.connect(self.generate_and_show_full_map)
        
        header_layout.addStretch()
        header_layout.addWidget(self.full_map_btn)
        header_layout.addSpacing(10)
        header_layout.addWidget(self.undo_btn)
        header_layout.addSpacing(10)
        header_layout.addWidget(self.add_row_btn)
        coords_layout.addLayout(header_layout)

        # Создаем таблицу
        self.coords_table = CoordTableWidget(0, 6, self)
        self.coords_table.setItemDelegateForColumn(1, TransparentTextDelegate(self.coords_table))
        
        # Устанавливаем кастомный заголовок с фильтрами
        self.filter_header = FilterHeader(self.coords_table)
        self.coords_table.setHorizontalHeader(self.filter_header)
        self.filter_header.filter_requested.connect(self.handle_filter_request)
        
        self.coords_table.setHorizontalHeaderLabels(["Название", "Координаты (X, Y)", "Погрешность", "Скрин", "Действие", "Удалить"])
        
        header = self.coords_table.horizontalHeader()
        self._is_resizing = True # Блокируем сигналы на время восстановления
        
        # Восстанавливаем состояние заголовков, используем новый ключ для сброса старого состояния
        state = self.settings_obj.value("coords_table_header_state_v5")
        if state:
            header.restoreState(state)
        else:
            # Размеры по умолчанию, если нет сохраненного состояния
            header.resizeSection(0, 150) # Название
            header.resizeSection(1, 150) # Координаты
            header.resizeSection(2, 80)  # Погрешность
            header.resizeSection(3, 60)  # Скрин
            header.resizeSection(4, 150) # Действие
            header.resizeSection(5, 60)  # Удалить

        # Форсируем интерактивный режим для первых 4 колонок
        for i in range(4):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
            
        # Применяем StretchLastSection ПОСЛЕ восстановления состояния, чтобы оно не перезаписалось
        header.setStretchLastSection(True)
            
        self._is_resizing = False
        header.sectionResized.connect(self.on_section_resized)
        
        self.coords_table.verticalHeader().setVisible(False)
        self.coords_table.verticalHeader().setDefaultSectionSize(45) # Увеличиваем высоту строки
        self.coords_table.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e2e;
                color: #cdd6f4;
                gridline-color: #313244;
                font-size: 14px;
                border: 1px solid #313244;
                border-radius: 4px;
            }
            QHeaderView::section {
                background-color: #181825;
                color: #cdd6f4;
                font-weight: bold;
                padding: 4px;
                border: 1px solid #313244;
            }
            QTableWidget::item {
                padding: 5px;
            }
        """)

        self.coords_list = []
        self.history_stack = [] # Стек для Undo
        self.current_picking_row = -1
        
        self.load_coords()
        self.coords_table.itemChanged.connect(self.save_coords)
        coords_layout.addWidget(self.coords_table)
        self.content_stack.addWidget(coords_page)

        # 3. Категория Карты
        item_maps = QListWidgetItem("Карты")
        self.category_list.addItem(item_maps)
        
        maps_page = QWidget()
        maps_layout = QVBoxLayout(maps_page)
        maps_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # --- Секция: Регион миникарты ---
        region_label = QLabel("Настройки миникарты (общие для всех карт)")
        region_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 10px;")
        maps_layout.addWidget(region_label)
        
        region_layout = QHBoxLayout()
        self.region_btn = QPushButton("Определить регион")
        self.region_btn.setStyleSheet("background-color: #89b4fa; color: #11111b; border-radius: 4px; padding: 6px 16px; font-weight: bold;")
        self.region_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.region_btn.clicked.connect(self.start_region_picking)
        
        self.region_val_label = QLabel(self.settings_obj.value("minimap_region", "Не задан", type=str))
        self.region_val_label.setStyleSheet("color: #a6e3a1; font-weight: bold;")
        
        region_layout.addWidget(self.region_btn)
        region_layout.addWidget(self.region_val_label)
        region_layout.addStretch()
        maps_layout.addLayout(region_layout)
        
        # --- Секция: Управление записью (в две строки) ---
        rec_section_vbox = QVBoxLayout()
        
        # Первая строка: Карта, Интервал, Радиус кисти
        rec_row1 = QHBoxLayout()
        rec_title = QLabel("Запись карты:")
        rec_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        
        self.rec_map_combo = QComboBox()
        self.rec_map_combo.setStyleSheet("padding: 5px; background-color: #181825; border: 1px solid #313244;")
        self.rec_map_combo.setFixedWidth(150)
        
        interval_label = QLabel("Интервал (мс):")
        self.rec_interval_spin = QSpinBox()
        self.rec_interval_spin.setRange(10, 5000)
        self.rec_interval_spin.setValue(self.settings_obj.value("rec_interval_ms", 500, type=int))
        self.rec_interval_spin.setSingleStep(10)
        self.rec_interval_spin.setStyleSheet("padding: 5px; background-color: #181825; border: 1px solid #313244;")
        self.rec_interval_spin.valueChanged.connect(lambda v: self.settings_obj.setValue("rec_interval_ms", v))

        brush_label = QLabel("Радиус кисти:")
        self.rec_brush_spin = QSpinBox()
        self.rec_brush_spin.setRange(0, 100)
        self.rec_brush_spin.setValue(self.settings_obj.value("rec_brush_radius", 4, type=int))
        self.rec_brush_spin.setStyleSheet("padding: 5px; background-color: #181825; border: 1px solid #313244;")
        self.rec_brush_spin.valueChanged.connect(lambda v: self.settings_obj.setValue("rec_brush_radius", v))

        rec_row1.addWidget(rec_title)
        rec_row1.addWidget(self.rec_map_combo)
        rec_row1.addSpacing(10)
        rec_row1.addWidget(interval_label)
        rec_row1.addWidget(self.rec_interval_spin)
        rec_row1.addSpacing(10)
        rec_row1.addWidget(brush_label)
        rec_row1.addWidget(self.rec_brush_spin)
        rec_row1.addStretch()
        
        # Вторая строка: Отступ, Цвет персонажа, Кнопки старт/стоп
        rec_row2 = QHBoxLayout()
        
        offset_label = QLabel("Отступ от стен (px):")
        self.nav_offset_spin = QSpinBox()
        self.nav_offset_spin.setRange(0, 50)
        self.nav_offset_spin.setValue(self.settings_obj.value("nav_wall_offset", 5, type=int))
        self.nav_offset_spin.setStyleSheet("padding: 5px; background-color: #181825; border: 1px solid #313244;")
        self.nav_offset_spin.valueChanged.connect(lambda v: self.settings_obj.setValue("nav_wall_offset", v))

        char_color_label = QLabel("Цвет персонажа:")
        self.char_color_btn = QPushButton()
        self.char_color_btn.setFixedSize(32, 32)
        char_color_hex = self.settings_obj.value("rec_char_color", "#00ff00", type=str)
        self.char_color_btn.setStyleSheet(f"background-color: {char_color_hex}; border-radius: 4px; border: 1px solid #313244;")
        self.char_color_btn.clicked.connect(self.pick_char_color)
        
        self.rec_start_btn = QPushButton("▶ Запись")
        self.rec_start_btn.setStyleSheet("background-color: #f38ba8; color: #11111b; font-weight: bold; padding: 5px 20px;")
        self.rec_start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rec_start_btn.clicked.connect(self.start_map_recording)
        
        self.rec_stop_btn = QPushButton("⏹ Стоп")
        self.rec_stop_btn.setStyleSheet("background-color: #89dceb; color: #11111b; font-weight: bold; padding: 5px 20px;")
        self.rec_stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rec_stop_btn.clicked.connect(self.stop_map_recording)
        self.rec_stop_btn.setEnabled(False)

        self.rec_reverse_btn = QPushButton("🔄 Реверс")
        self.rec_reverse_btn.setCheckable(True)
        self.rec_reverse_btn.setStyleSheet("""
            QPushButton { 
                background-color: #f38ba8; 
                color: #11111b; 
                border-radius: 4px; 
                padding: 5px 15px; 
                font-weight: bold; 
            }
            QPushButton:checked { 
                background-color: #a6e3a1; 
                color: #11111b; 
            }
        """)
        self.rec_reverse_btn.setToolTip("ВКЛ: Рисовать ЧЕРНЫМ (препятствия) / ВЫКЛ: Рисовать БЕЛЫМ (путь)")
        self.rec_reverse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rec_reverse_btn.toggled.connect(lambda checked: setattr(self.map_recorder, 'is_reverse', checked))
        
        rec_row2.addWidget(offset_label)
        rec_row2.addWidget(self.nav_offset_spin)
        rec_row2.addSpacing(10)
        rec_row2.addWidget(char_color_label)
        rec_row2.addWidget(self.char_color_btn)
        rec_row2.addSpacing(20)
        rec_row2.addWidget(self.rec_reverse_btn)
        rec_row2.addWidget(self.rec_start_btn)
        rec_row2.addWidget(self.rec_stop_btn)
        rec_row2.addStretch()
        
        rec_section_vbox.addLayout(rec_row1)
        rec_section_vbox.addLayout(rec_row2)
        maps_layout.addLayout(rec_section_vbox)
        
        # --- Секция: Менеджер карт ---
        maps_list_label = QLabel("Менеджер карт")
        maps_list_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 20px;")
        maps_layout.addWidget(maps_list_label)
        
        maps_mgr_layout = QHBoxLayout()
        
        # Список карт
        self.maps_list_widget = QListWidget()
        self.maps_list_widget.setFixedWidth(200)
        self.maps_list_widget.setStyleSheet("background-color: #1e1e2e; color: #cdd6f4; border: 1px solid #313244; border-radius: 4px;")
        self.maps_list_widget.itemSelectionChanged.connect(self.on_map_selected)
        self.load_maps_list()
        
        # Кнопки под списком
        maps_btns_layout = QVBoxLayout()
        
        add_map_btn = QPushButton(" + Создать карту")
        add_map_btn.setStyleSheet("background-color: #a6e3a1; color: #11111b; border-radius: 4px; padding: 6px; font-weight: bold;")
        add_map_btn.clicked.connect(self.add_map)
        
        del_map_btn = QPushButton("🗑 Удалить")
        del_map_btn.setStyleSheet("background-color: #f38ba8; color: #11111b; border-radius: 4px; padding: 6px; font-weight: bold;")
        del_map_btn.clicked.connect(self.delete_map)
        
        refresh_map_btn = QPushButton("🔄 Обновить")
        refresh_map_btn.setStyleSheet("background-color: #89dceb; color: #11111b; border-radius: 4px; padding: 6px; font-weight: bold;")
        refresh_map_btn.setToolTip("Обновить превью из файла (если вы редактировали его вручную)")
        refresh_map_btn.clicked.connect(self.on_map_selected)
        
        maps_btns_layout.addWidget(add_map_btn)
        maps_btns_layout.addWidget(del_map_btn)
        maps_btns_layout.addWidget(refresh_map_btn)
        maps_btns_layout.addStretch()
        
        # Превью карты
        preview_layout = QVBoxLayout()
        self.map_preview_label = QLabel("Выберите карту для предпросмотра")
        self.map_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.map_preview_label.setStyleSheet("background-color: #11111b; border: 1px solid #313244; min-width: 300px; min-height: 300px;")
        
        self.open_editor_btn = QPushButton("Открыть в редакторе")
        self.open_editor_btn.setStyleSheet("background-color: #cba6f7; color: #11111b; border-radius: 4px; padding: 6px; font-weight: bold; margin-top: 10px;")
        self.open_editor_btn.clicked.connect(self.open_map_editor)
        self.open_editor_btn.hide()
        
        preview_layout.addWidget(self.map_preview_label)
        preview_layout.addWidget(self.open_editor_btn)
        preview_layout.addStretch()
        
        # Тестовый бег (справа от превью)
        test_move_layout = QVBoxLayout()
        
        test_header_layout = QHBoxLayout()
        test_move_label = QLabel("Тестовый бег")
        test_move_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 10px;")
        
        self.cb_save_debug_map = QCheckBox()
        self.cb_save_debug_map.setChecked(self.settings_obj.value("save_debug_map", False, type=bool))
        self.cb_save_debug_map.setStyleSheet("margin-top: 10px;")
        self.cb_save_debug_map.stateChanged.connect(lambda state: self.settings_obj.setValue("save_debug_map", state == 2))
        
        self.btn_passive_record = QPushButton("🔍")
        self.btn_passive_record.setToolTip("Пассивная запись траектории ручного бега")
        self.btn_passive_record.setFixedSize(24, 24)
        self.btn_passive_record.setStyleSheet("background-color: #f5c2e7; color: #11111b; font-weight: bold; border-radius: 4px; margin-top: 10px;")
        self.btn_passive_record.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_passive_record.clicked.connect(self.run_passive_test_move)

        test_header_layout.addWidget(test_move_label)
        test_header_layout.addWidget(self.cb_save_debug_map)
        test_header_layout.addWidget(self.btn_passive_record)
        test_header_layout.addStretch()
        
        self.test_coords_input = QLineEdit()
        self.test_coords_input.setPlaceholderText("Вставьте X, Y (напр. 100, 200)")
        self.test_coords_input.setStyleSheet("padding: 8px; background-color: #1e1e2e; color: #cdd6f4; border: 1px solid #313244; border-radius: 4px;")
        
        test_run_btn = QPushButton("Проверить путь (Ок)")
        test_run_btn.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-weight: bold; padding: 10px; margin-top: 5px;")
        test_run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        test_run_btn.clicked.connect(self.run_test_move)
        
        test_move_layout.addLayout(test_header_layout)
        test_move_layout.addWidget(self.test_coords_input)
        test_move_layout.addWidget(test_run_btn)

        # Смещение карты (Коррекция центрирования)
        shift_label = QLabel("Коррекция центрирования")
        shift_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 20px;")

        was_layout = QHBoxLayout()
        was_title = QLabel("Было:")
        self.shift_was_val = QLabel("0, 0")
        self.shift_was_val.setStyleSheet("color: #fab387; font-weight: bold;")
        was_layout.addWidget(was_title)
        was_layout.addWidget(self.shift_was_val)
        was_layout.addStretch()

        become_layout = QHBoxLayout()
        become_title = QLabel("Стало:")
        self.shift_x_spin = QSpinBox()
        self.shift_y_spin = QSpinBox()
        for sb in [self.shift_x_spin, self.shift_y_spin]:
            sb.setRange(-2000, 2000)
            sb.setStyleSheet("background-color: #1e1e2e; color: #cdd6f4; padding: 5px;")

        become_layout.addWidget(become_title)
        become_layout.addWidget(QLabel("X:"))
        become_layout.addWidget(self.shift_x_spin)
        become_layout.addWidget(QLabel("Y:"))
        become_layout.addWidget(self.shift_y_spin)

        self.shift_btn = QPushButton("Сместить пути")
        self.shift_btn.setStyleSheet("background-color: #f9e2af; color: #11111b; font-weight: bold; padding: 8px; margin-top: 10px;")
        self.shift_btn.clicked.connect(self.shift_map_paths)

        test_move_layout.addWidget(shift_label)
        test_move_layout.addLayout(was_layout)
        test_move_layout.addLayout(become_layout)
        test_move_layout.addWidget(self.shift_btn)

        test_move_layout.addStretch()
        maps_mgr_layout.addWidget(self.maps_list_widget)
        maps_mgr_layout.addLayout(maps_btns_layout)
        maps_mgr_layout.addLayout(preview_layout)
        maps_mgr_layout.addLayout(test_move_layout)
        maps_mgr_layout.addStretch()
        
        maps_layout.addLayout(maps_mgr_layout)
        self.content_stack.addWidget(maps_page)

        # 4. Категория Передвижение
        item_move = QListWidgetItem("Передвижение")
        self.category_list.addItem(item_move)
        
        move_page = QWidget()
        move_layout = QVBoxLayout(move_page)
        move_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        move_layout.setContentsMargins(15, 8, 15, 8)
        
        move_title = QLabel("Настройки навигации и движения")
        move_title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 5px;")
        move_layout.addWidget(move_title)
        
        # Сетка для настроек
        move_grid = QGridLayout()
        move_grid.setVerticalSpacing(6)
        move_grid.setHorizontalSpacing(10)
        move_grid.setColumnStretch(0, 0)
        move_grid.setColumnStretch(1, 1)
        
        def add_setting_row(label_text, spinbox, tooltip_text, row):
            label = QLabel(label_text)
            label.setStyleSheet("font-size: 14px;")
            
            spinbox.setFixedWidth(80)
            
            help_btn = QPushButton("?")
            help_btn.setFixedSize(28, 28)
            help_btn.setToolTip(tooltip_text)
            help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            help_btn.setStyleSheet("""
                QPushButton {
                    background-color: #313244;
                    color: #cdd6f4;
                    border: 1px solid #45475a;
                    border-radius: 4px;
                    font-weight: bold;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #45475a;
                    color: #f9e2af;
                }
            """)
            help_btn.clicked.connect(lambda: self.show_help_dialog(label_text, tooltip_text))
            
            # Контейнер для поля ввода и знака вопроса, прижатый влево
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            row_layout.addWidget(spinbox)
            row_layout.addWidget(help_btn)
            row_layout.addStretch()
            
            move_grid.addWidget(label, row, 0)
            move_grid.addWidget(row_widget, row, 1)
            
        # Интервал сканирования
        self.scan_interval_spin = QSpinBox()
        self.scan_interval_spin.setRange(20, 1000)
        self.scan_interval_spin.setValue(self.settings_obj.value("nav_scan_interval", 100, type=int))
        self.scan_interval_spin.setSingleStep(10)
        self.scan_interval_spin.setStyleSheet("padding: 4px; background-color: #181825; border: 1px solid #313244; color: #cdd6f4;")
        self.scan_interval_spin.valueChanged.connect(lambda v: self.settings_obj.setValue("nav_scan_interval", v))
        add_setting_row(
            "Интервал сканирования миникарты (мс):", 
            self.scan_interval_spin, 
            "Частота анализа скриншота миникарты. Меньше значение — быстрее реакция бота, но выше нагрузка на процессор. Рекомендуется 100 мс.",
            0
        )
        
        # Погрешность цели
        self.target_tolerance_spin = QSpinBox()
        self.target_tolerance_spin.setRange(0, 100)
        self.target_tolerance_spin.setValue(self.settings_obj.value("nav_target_tolerance", 10, type=int))
        self.target_tolerance_spin.setStyleSheet("padding: 4px; background-color: #181825; border: 1px solid #313244; color: #cdd6f4;")
        self.target_tolerance_spin.valueChanged.connect(lambda v: self.settings_obj.setValue("nav_target_tolerance", v))
        add_setting_row(
            "Погрешность прибытия в точку (px):",
            self.target_tolerance_spin,
            "Радиус зоны вокруг конечной цели на миникарте, при достижении которой движение считается завершенным.",
            1
        )
        
        # Порог переключения по прямой
        self.wp_straight_spin = QDoubleSpinBox()
        self.wp_straight_spin.setRange(0.0, 20.0)
        self.wp_straight_spin.setSingleStep(0.5)
        self.wp_straight_spin.setDecimals(1)
        self.wp_straight_spin.setValue(float(self.settings_obj.value("nav_wp_straight", 4.0)))
        self.wp_straight_spin.setStyleSheet("padding: 4px; background-color: #181825; border: 1px solid #313244; color: #cdd6f4;")
        self.wp_straight_spin.valueChanged.connect(lambda v: self.settings_obj.setValue("nav_wp_straight", v))
        add_setting_row(
            "Порог переключения по прямой (px):",
            self.wp_straight_spin,
            "Расстояние до следующего вейпоинта на прямых участках, при достижении которого бот начинает целиться на следующий ориентир.",
            2
        )
        
        # Порог переключения на поворотах
        self.wp_turn_spin = QDoubleSpinBox()
        self.wp_turn_spin.setRange(0.0, 20.0)
        self.wp_turn_spin.setSingleStep(0.5)
        self.wp_turn_spin.setDecimals(1)
        self.wp_turn_spin.setValue(float(self.settings_obj.value("nav_wp_turn", 1.8)))
        self.wp_turn_spin.setStyleSheet("padding: 4px; background-color: #181825; border: 1px solid #313244; color: #cdd6f4;")
        self.wp_turn_spin.valueChanged.connect(lambda v: self.settings_obj.setValue("nav_wp_turn", v))
        add_setting_row(
            "Порог переключения на поворотах (px):",
            self.wp_turn_spin,
            "Расстояние до вейпоинта на крутом повороте. Бот должен подойти ближе к углу перед тем, как переключиться на следующий шаг.",
            3
        )
        
        # Тормозной путь
        self.early_stop_spin = QDoubleSpinBox()
        self.early_stop_spin.setRange(0.0, 20.0)
        self.early_stop_spin.setSingleStep(0.5)
        self.early_stop_spin.setDecimals(1)
        self.early_stop_spin.setValue(float(self.settings_obj.value("nav_early_stop", 0.0)))
        self.early_stop_spin.setStyleSheet("padding: 4px; background-color: #181825; border: 1px solid #313244; color: #cdd6f4;")
        self.early_stop_spin.valueChanged.connect(lambda v: self.settings_obj.setValue("nav_early_stop", v))
        add_setting_row(
            "Тормозной путь (ранняя остановка, px):",
            self.early_stop_spin,
            "Дистанция до финальной цели, на которой бот полностью отпустит джойстик, позволяя персонажу докатиться по инерции.",
            4
        )
        
        # Дистанция взгляда по прямой
        self.lookahead_straight_spin = QDoubleSpinBox()
        self.lookahead_straight_spin.setRange(1.0, 50.0)
        self.lookahead_straight_spin.setSingleStep(0.5)
        self.lookahead_straight_spin.setDecimals(1)
        self.lookahead_straight_spin.setValue(float(self.settings_obj.value("nav_lookahead_straight", 5.5)))
        self.lookahead_straight_spin.setStyleSheet("padding: 4px; background-color: #181825; border: 1px solid #313244; color: #cdd6f4;")
        self.lookahead_straight_spin.valueChanged.connect(lambda v: self.settings_obj.setValue("nav_lookahead_straight", v))
        add_setting_row(
            "Дистанция взгляда по прямой (px):",
            self.lookahead_straight_spin,
            "Расстояние упреждения пути (lookahead) на прямых отрезках. Задает упреждающую цель движения по траектории.",
            5
        )

        # Мин. дистанция взгляда на повороте
        self.lookahead_turn_min_spin = QDoubleSpinBox()
        self.lookahead_turn_min_spin.setRange(0.5, 20.0)
        self.lookahead_turn_min_spin.setSingleStep(0.1)
        self.lookahead_turn_min_spin.setDecimals(1)
        self.lookahead_turn_min_spin.setValue(float(self.settings_obj.value("nav_lookahead_turn_min", 1.5)))
        self.lookahead_turn_min_spin.setStyleSheet("padding: 4px; background-color: #181825; border: 1px solid #313244; color: #cdd6f4;")
        self.lookahead_turn_min_spin.valueChanged.connect(lambda v: self.settings_obj.setValue("nav_lookahead_turn_min", v))
        add_setting_row(
            "Мин. дистанция взгляда на повороте (px):",
            self.lookahead_turn_min_spin,
            "Минимальное расстояние упреждения (lookahead) перед крутыми поворотами. Помогает точнее вписываться в углы.",
            6
        )

        # Пауза Stop-and-Turn
        self.stop_turn_pause_spin = QSpinBox()
        self.stop_turn_pause_spin.setRange(0, 2000)
        self.stop_turn_pause_spin.setSingleStep(50)
        self.stop_turn_pause_spin.setValue(int(self.settings_obj.value("nav_stop_turn_pause", 150)))
        self.stop_turn_pause_spin.setStyleSheet("padding: 4px; background-color: #181825; border: 1px solid #313244; color: #cdd6f4;")
        self.stop_turn_pause_spin.valueChanged.connect(lambda v: self.settings_obj.setValue("nav_stop_turn_pause", v))
        add_setting_row(
            "Пауза Stop-and-Turn (мс):",
            self.stop_turn_pause_spin,
            "Временная микропауза при прохождении крутых углов для полной остановки персонажа и устранения инерционного заноса.",
            7
        )
        
        # Смещение точек по X на карте
        self.map_shift_x_spin = QSpinBox()
        self.map_shift_x_spin.setRange(-100, 100)
        self.map_shift_x_spin.setValue(self.settings_obj.value("map_draw_shift_x", 10, type=int))
        self.map_shift_x_spin.setStyleSheet("padding: 4px; background-color: #181825; border: 1px solid #313244; color: #cdd6f4;")
        self.map_shift_x_spin.valueChanged.connect(lambda v: self.settings_obj.setValue("map_draw_shift_x", v))
        add_setting_row(
            "Смещение точек по X на карте (px):",
            self.map_shift_x_spin,
            "Смещение отрисовки траектории по горизонтали относительно миникарты для точного центрирования.",
            8
        )
        
        # Смещение точек по Y на карте
        self.map_shift_y_spin = QSpinBox()
        self.map_shift_y_spin.setRange(-100, 100)
        self.map_shift_y_spin.setValue(self.settings_obj.value("map_draw_shift_y", 0, type=int))
        self.map_shift_y_spin.setStyleSheet("padding: 4px; background-color: #181825; border: 1px solid #313244; color: #cdd6f4;")
        self.map_shift_y_spin.valueChanged.connect(lambda v: self.settings_obj.setValue("map_draw_shift_y", v))
        add_setting_row(
            "Смещение точек по Y на карте (px):",
            self.map_shift_y_spin,
            "Смещение отрисовки траектории по вертикали относительно миникарты для точного центрирования.",
            9
        )
        
        move_layout.addLayout(move_grid)
        move_layout.addStretch()
        
        self.content_stack.addWidget(move_page)

        # По умолчанию выбираем первую категорию
        self.category_list.setCurrentRow(0)

    def show_help_dialog(self, title, text):
        popup = HelpPopup(self, title, text)
        popup.exec()

    def on_coords_tab_changed(self, tab_id):
        tab_keys = ["buttons", "bosses", "chests", "gifts"]
        if 0 <= tab_id < len(tab_keys):
            base_tab = tab_keys[tab_id]
            if base_tab == "buttons":
                self.subtabs_container.hide()
                if hasattr(self, 'full_map_btn'): self.full_map_btn.hide()
                self.current_coords_tab = "buttons"
            else:
                self.subtabs_container.show()
                if hasattr(self, 'full_map_btn'): self.full_map_btn.show()
                self.current_coords_tab = f"{base_tab}_{self.current_subtab_index}"
                self.update_subtabs_ui()
                
            self.load_coords()
            # Если тест включен, обновляем его данные тоже
            if self.test_btn.isChecked():
                self.toggle_test_overlay(True)

    def update_subtabs_ui(self):
        print(f"DEBUG: update_subtabs_ui called. coords_subtabs_count = {self.coords_subtabs_count}")
        # Очищаем старые кнопки
        while self.subtabs_layout.count():
            item = self.subtabs_layout.takeAt(0)
            if item.widget():
                if item.widget() in self.subtabs_group.buttons():
                    self.subtabs_group.removeButton(item.widget())
                item.widget().deleteLater()
                
        # Добавляем кнопки с номерами
        print("DEBUG: Adding number buttons...")
        for i in range(1, self.coords_subtabs_count + 1):
            print(f"DEBUG: Adding button {i}")
            btn = QPushButton(str(i))
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(32, 32)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #181825;
                    color: #cdd6f4;
                    border: 2px solid #f9e2af;
                    border-radius: 4px;
                    font-weight: bold;
                    font-size: 14px;
                }
                QPushButton:hover { background-color: #313244; }
                QPushButton:checked {
                    background-color: #f9e2af;
                    color: #11111b;
                }
            """)
            self.subtabs_group.addButton(btn, i)
            self.subtabs_layout.addWidget(btn)
            if i == self.current_subtab_index:
                btn.setChecked(True)
                
        # Кнопка Плюс
        print("DEBUG: Adding plus and minus buttons...")
        plus_btn = QPushButton("+")
        plus_btn.setFixedSize(32, 32)
        plus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        plus_btn.setStyleSheet("""
            QPushButton {
                background-color: #181825; color: #a6e3a1; border: 2px solid #a6e3a1; border-radius: 4px; font-weight: bold; font-size: 18px;
            }
            QPushButton:hover { background-color: #313244; }
        """)
        plus_btn.clicked.connect(self.add_subtab)
        self.subtabs_layout.addWidget(plus_btn)
        
        # Кнопка Минус
        minus_btn = QPushButton("-")
        minus_btn.setFixedSize(32, 32)
        minus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        minus_btn.setStyleSheet("""
            QPushButton {
                background-color: #181825; color: #f38ba8; border: 2px solid #f38ba8; border-radius: 4px; font-weight: bold; font-size: 18px;
            }
            QPushButton:hover { background-color: #313244; }
        """)
        minus_btn.clicked.connect(self.remove_subtab)
        self.subtabs_layout.addWidget(minus_btn)
        
        self.subtabs_layout.addStretch()
        print(f"DEBUG: update_subtabs_ui finished. Layout count: {self.subtabs_layout.count()}")

    def on_subtab_clicked(self, subtab_id):
        self.current_subtab_index = subtab_id
        self.settings_obj.setValue("current_subtab_index", subtab_id)
        
        # Обновляем ключ текущей вкладки (base_tab берем из главной вкладки)
        tab_id = self.coords_tabs_group.checkedId()
        tab_keys = ["buttons", "bosses", "chests", "gifts"]
        if 1 <= tab_id < len(tab_keys):
            self.current_coords_tab = f"{tab_keys[tab_id]}_{self.current_subtab_index}"
            self.load_coords()

    def add_subtab(self):
        if self.coords_subtabs_count >= 10:
            QMessageBox.information(self, "Лимит", "Достигнут лимит в 10 подвкладок.")
            return
        self.coords_subtabs_count += 1
        self.settings_obj.setValue("coords_subtabs_count", self.coords_subtabs_count)
        self.update_subtabs_ui()

    def remove_subtab(self):
        if self.coords_subtabs_count <= 1:
            QMessageBox.warning(self, "Ошибка", "Нельзя удалить последнюю подвкладку!")
            return
            
        # Удаляем данные последней вкладки для всех категорий
        tab_keys = ["bosses", "chests", "gifts"]
        for tab in tab_keys:
            key_to_remove = f"coords_list_{tab}_{self.coords_subtabs_count}"
            self.settings_obj.remove(key_to_remove)
            
        self.coords_subtabs_count -= 1
        self.settings_obj.setValue("coords_subtabs_count", self.coords_subtabs_count)
        
        if self.current_subtab_index > self.coords_subtabs_count:
            # Переключаемся на предыдущую если мы были на удаленной
            self.subtabs_group.button(self.coords_subtabs_count).setChecked(True)
            self.on_subtab_clicked(self.coords_subtabs_count)
        else:
            self.update_subtabs_ui()

    def on_threshold_changed(self, value):
        self.thresh_label.setText(f"Уверенность (Threshold): {value}%")
        self.settings_obj.setValue("match_threshold", str(value))
        
    def choose_mask_color(self):
        current_color = QColor(self.settings_obj.value("mask_color", "#00ff00", type=str))
        color = QColorDialog.getColor(current_color, self, "Выберите цвет для прозрачных пикселей")
        if color.isValid():
            hex_color = color.name()
            self.settings_obj.setValue("mask_color", hex_color)
            self.mask_color_btn.setStyleSheet(f"background-color: {hex_color}; color: black; font-weight: bold; border-radius: 4px; padding: 4px;")
            self.interactive_map.load_image() # Перезагружаем картинку с новым цветом маски

    def load_coords(self):
        key = f"coords_list_{self.current_coords_tab}"
        coords_json = self.settings_obj.value(key, "[]", type=str)
        try:
            self.coords_list = json.loads(coords_json)
        except json.JSONDecodeError:
            self.coords_list = []
            
        self.coords_table.setRowCount(0)
        # Блокируем сигналы, чтобы заполнение таблицы не вызывало автоматическое сохранение
        self.coords_table.blockSignals(True)
        for row, target in enumerate(self.coords_list):
            self.insert_row_ui(row, target)
        self.coords_table.blockSignals(False)


    def pick_crosshair_color(self):
        color = QColorDialog.getColor(QColor(self.settings_obj.value("test_crosshair_color", "#ff0000")))
        if color.isValid():
            hex_color = color.name()
            self.settings_obj.setValue("test_crosshair_color", hex_color)
            self.crosshair_color_btn.setStyleSheet(f"background-color: {hex_color}; border-radius: 4px; border: 2px solid #313244;")
            if self.test_btn.isChecked():
                self.toggle_test_overlay(True)

    def on_crosshair_settings_changed(self, value):
        self.settings_obj.setValue("test_crosshair_length", value)
        if self.test_btn.isChecked():
            self.toggle_test_overlay(True)

    def save_header_state(self):
        header = self.coords_table.horizontalHeader()
        self.settings_obj.setValue("coords_table_header_state_v5", header.saveState())

    def toggle_editor_mode(self):
        if self.interactive_map.mode == "center":
            self.interactive_map.mode = "erase"
            self.interactive_map.setCursor(Qt.CursorShape.CrossCursor)
            self.mode_btn.setText("Режим: ЛАСТИК")
            self.mode_btn.setStyleSheet("background-color: #f38ba8; color: #11111b; font-weight: bold; padding: 6px;")
            self.save_mask_btn.show()
            self.reset_mask_btn.show()
            self.edit_warning.show()
        else:
            self.interactive_map.mode = "center"
            self.interactive_map.setCursor(Qt.CursorShape.ArrowCursor)
            self.mode_btn.setText("Режим: Центрирование")
            self.mode_btn.setStyleSheet("background-color: #313244; color: #cdd6f4; font-weight: bold; padding: 6px; border: 1px solid #45475a;")
            self.save_mask_btn.hide()
            self.reset_mask_btn.hide()
            self.edit_warning.hide()

    def on_eraser_size_changed(self, value):
        self.interactive_map.eraser_size = value

    def save_marker_mask(self):
        if self.interactive_map.save_mask():
            QMessageBox.information(self, "Успех", "Маска маркера сохранена.")
            # Также обновляем в MapRecorder
            self.map_recorder.load_marker()
        else:
            QMessageBox.warning(self, "Ошибка", "Не удалось сохранить маску")

    def reset_marker_mask(self):
        self.interactive_map.reset_mask()
        QMessageBox.information(self, "Сброс", "Изменения отменены")

    def capture_marker_from_screen(self):
        self.main_window.showMinimized()
        
        def show_picker():
            # Используем PickerOverlay для выбора точки на экране
            self.picker = PickerOverlay()
            # Правильное название сигнала: coordinate_picked, а не point_selected
            self.picker.coordinate_picked.connect(self.on_marker_point_selected)
            self.picker.show()
            
        # Даем окну время свернуться без блокировки главного потока
        QTimer.singleShot(400, show_picker)

    def on_marker_point_selected(self, x, y):
        # Получаем коэффициент масштабирования экрана (DPI)
        screen = QApplication.primaryScreen()
        scale = screen.devicePixelRatio() if screen else 1.0
        
        # Переводим логические координаты клика в физические для mss
        phys_x = int(x * scale)
        phys_y = int(y * scale)
        
        # Получаем размер захвата из настроек
        size_logical = self.capture_size_spin.value()
        size_phys = int(size_logical * scale)
        
        region = {
            "top": int(phys_y - size_phys // 2),
            "left": int(phys_x - size_phys // 2),
            "width": size_phys,
            "height": size_phys
        }
        
        print(f"[DEBUG] Click logical: ({x}, {y}), scale: {scale}, physical: ({phys_x}, {phys_y}), size: {size_phys}")
        
        def do_grab():
            try:
                with mss.mss() as sct:
                    sct_img = sct.grab(region)
                    img = np.array(sct_img)
                    cv2.imwrite(self.interactive_map.image_path, img)
            except Exception as e:
                print(f"[ERROR] Capture failed: {e}")
                
            self.main_window.showNormal()
            self.main_window.activateWindow()
            
            # Перезагружаем виджет
            self.interactive_map.load_image()
            
            def show_done_dialog():
                msg = QMessageBox(self)
                msg.setWindowTitle("Успех")
                msg.setText(f"Маркер захвачен! (Scale: {scale})\nЕсли смещено, попробуйте изменить масштаб Windows на 100%.")
                msg.setStyleSheet("color: black;")
                msg.exec()
                
            QTimer.singleShot(200, show_done_dialog)
            
        # Ожидаем 200мс чтобы оверлей успел полностью закрыться
        QTimer.singleShot(200, do_grab)

    def on_auto_crop_clicked(self):
        if self.interactive_map.auto_crop():
            # Также обновляем в MapRecorder
            self.map_recorder.load_marker()
            
            msg = QMessageBox(self)
            msg.setWindowTitle("Обрезка")
            msg.setText("Края успешно обрезаны! Маркер теперь максимально прижат к границам.")
            msg.setStyleSheet("color: black;")
            msg.exec()

    def handle_filter_request(self, index, action, value):
        if action == "sort":
            self.coords_table.setSortingEnabled(True)
            self.coords_table.sortByColumn(index, value)
            self.coords_table.setSortingEnabled(False)
            # После сортировки сохраняем упорядоченный список
            self.save_coords()
            # Обновляем индексы строк в лямбда-функциях кнопок
            self.refresh_row_buttons()
        elif action == "filter_contains":
            for row in range(self.coords_table.rowCount()):
                item = self.coords_table.item(row, index)
                # Для колонок с виджетами (SpinBox) получаем значение иначе
                text = ""
                if item:
                    text = item.text().lower()
                else:
                    widget = get_inner_widget(self.coords_table.cellWidget(row, index))
                    if isinstance(widget, QSpinBox):
                        text = str(widget.value())
                
                if value.lower() in text:
                    self.coords_table.setRowHidden(row, False)
                else:
                    self.coords_table.setRowHidden(row, True)
        elif action == "filter_not_contains":
            for row in range(self.coords_table.rowCount()):
                item = self.coords_table.item(row, index)
                text = ""
                if item:
                    text = item.text().lower()
                else:
                    widget = get_inner_widget(self.coords_table.cellWidget(row, index))
                    if isinstance(widget, QSpinBox):
                        text = str(widget.value())
                
                if value.lower() not in text:
                    self.coords_table.setRowHidden(row, False)
                else:
                    self.coords_table.setRowHidden(row, True)
        elif action == "clear":
            for row in range(self.coords_table.rowCount()):
                self.coords_table.setRowHidden(row, False)

    def on_section_resized(self, logicalIndex, oldSize, newSize):
        if getattr(self, '_is_resizing', False): 
            return
            
        # Если мы меняем последнюю колонку, ничего не компенсируем
        if logicalIndex >= self.coords_table.columnCount() - 1:
            self.save_header_state()
            return
            
        delta = newSize - oldSize
        next_index = logicalIndex + 1
        
        header = self.coords_table.horizontalHeader()
        next_size = header.sectionSize(next_index)
        
        # Защита от схлопывания соседней колонки
        min_size = 40
        if next_size - delta < min_size:
            self._is_resizing = True
            header.resizeSection(logicalIndex, oldSize) # Откатываем назад
            self._is_resizing = False
        else:
            self._is_resizing = True
            header.resizeSection(next_index, next_size - delta)
            self._is_resizing = False
            
        self.save_header_state()

    def show_screenshot(self, row):
        name_item = self.coords_table.item(row, 0)
        if not name_item: return
        name = name_item.text()
        filename = f"{self.current_coords_tab}_{name}.png"
        path = os.path.join(SCREENSHOTS_DIR, filename)
        
        if os.path.exists(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                self.screenshot_viewer = FullScreenImageViewer(pixmap)
        else:
            QMessageBox.information(self, "Инфо", "Скриншот еще не сделан. Используйте 'Опред+' для автоматического захвата.")

    def rename_screenshot(self, old_name, new_name):
        if not old_name or not new_name or old_name == new_name:
            return
            
        old_filename = f"{self.current_coords_tab}_{old_name}.png"
        new_filename = f"{self.current_coords_tab}_{new_name}.png"
        
        old_path = os.path.join(SCREENSHOTS_DIR, old_filename)
        new_path = os.path.join(SCREENSHOTS_DIR, new_filename)
        
        if os.path.exists(old_path):
            try:
                if os.path.exists(new_path):
                    os.remove(new_path)
                os.rename(old_path, new_path)
            except Exception as e:
                print(f"Error renaming screenshot: {e}")

    def generate_and_show_full_map(self):
        if self.current_coords_tab == "buttons":
            return
            
        base_tab_parts = self.current_coords_tab.split('_')
        base_tab = base_tab_parts[0]
        subtab = base_tab_parts[1] if len(base_tab_parts) > 1 else "1"
        
        # 1. Автоматически находим папку оригинальной карты по номеру подвкладки (например, "3" -> "Глава 3")
        map_name = None
        maps_root = os.path.join(ASSETS_DIR, "maps")
        if os.path.exists(maps_root):
            for d in os.listdir(maps_root):
                if os.path.isdir(os.path.join(maps_root, d)):
                    if subtab in d:
                        map_name = d
                        break
                        
        if not map_name:
            QMessageBox.warning(self, "Ошибка", f"Не удалось автоматически найти папку карты для главы {subtab} в папке assets/maps! Создайте и задайте регион карты сначала.")
            return
            
        map_dir = os.path.join(ASSETS_DIR, "maps", map_name)
        original_map_path = os.path.join(map_dir, "map_original.png")
        region_info_path = os.path.join(map_dir, "region.json")
        
        if not os.path.exists(original_map_path) or not os.path.exists(region_info_path):
            QMessageBox.warning(self, "Ошибка", f"В папке карты '{map_name}' не найден файл map_original.png или region.json!")
            return
            
        try:
            # 2. Загружаем регион и масштаб
            with open(region_info_path, "r") as f:
                region = json.load(f)
                
            scale = region.get("scale", 1.0)
            
            # 3. Загружаем чистый оригинальный полноэкранный скриншот безопасным способом (поддержка кириллицы)
            with open(original_map_path, "rb") as f:
                chunk = np.frombuffer(f.read(), dtype=np.uint8)
                base_img = cv2.imdecode(chunk, cv2.IMREAD_COLOR)
                
            if base_img is None:
                QMessageBox.warning(self, "Ошибка", f"Не удалось прочитать {original_map_path}")
                return
                
            # 4. Рисуем зеленые закрашенные кружки с названиями точек внутри
            # Установим комфортный радиус для размещения текста внутри (8 логических пикселей -> диаметр 24 физических)
            circle_radius = int(8 * scale)
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.26
            font_thickness = 1
            
            shift_x = int(self.settings_obj.value("map_draw_shift_x", 10, type=int))
            shift_y = int(self.settings_obj.value("map_draw_shift_y", 0, type=int))
            
            for t in self.coords_list:
                x, y = t.get("x", 0), t.get("y", 0)
                name = t.get("name", "")
                
                # Переводим логические координаты в физические на полноэкранной карте (с учетом компенсации DWM)
                img_x = round((x + shift_x) * scale)
                img_y = round((y + shift_y) * scale)
                
                # Рисуем красивый закрашенный зеленый кружок
                cv2.circle(base_img, (img_x, img_y), circle_radius, (120, 220, 120), -1)
                # Рисуем аккуратную темно-зеленую обводку
                cv2.circle(base_img, (img_x, img_y), circle_radius, (40, 120, 40), 1)
                
                # Вычисляем точный размер текста для идеального центрирования внутри круга
                text_size = cv2.getTextSize(name, font, font_scale, font_thickness)[0]
                text_w, text_h = text_size[0], text_size[1]
                
                # Центрируем текст по осям X и Y
                tx = img_x - text_w // 2
                ty = img_y + text_h // 2
                
                # Пишем текст черным цветом
                cv2.putText(base_img, name, (tx, ty), font, font_scale, (0, 0, 0), font_thickness, cv2.LINE_AA)
                
            # 5. Обрезаем картинку по региону миникарты из region.json
            rx = int(region["x"] * scale)
            ry = int(region["y"] * scale)
            rw = int(region["w"] * scale)
            rh = int(region["h"] * scale)
            
            y2 = min(base_img.shape[0], ry + rh)
            x2 = min(base_img.shape[1], rx + rw)
            
            cropped_img = base_img[ry:y2, rx:x2]
            
            # 6. Сохраняем готовую красивую карту безопасным способом (поддержка кириллицы)
            collective_dir = os.path.join(ASSETS_DIR, "collective image", subtab)
            os.makedirs(collective_dir, exist_ok=True)
            out_path = os.path.join(collective_dir, f"{base_tab}.png")
            
            is_success, buffer = cv2.imencode(".png", cropped_img)
            if is_success:
                with open(out_path, "wb") as f:
                    f.write(buffer)
            else:
                QMessageBox.warning(self, "Ошибка", "Не удалось закодировать итоговое изображение!")
                return
            
            # 7. Отображение убрано по просьбе пользователя (работа в тихом режиме)
            pass
                
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сгенерировать карту из оригинала: {e}")

    def save_coords(self, *args):
        # Обновляем self.coords_list из UI
        new_list = []
        for row in range(self.coords_table.rowCount()):
            name_item = self.coords_table.item(row, 0)
            coord_item = self.coords_table.item(row, 1)
            wrapper = self.coords_table.cellWidget(row, 1)
            coord_widget = get_inner_widget(wrapper)
            spinbox = get_inner_widget(self.coords_table.cellWidget(row, 2))
            
            # Если еще не все элементы созданы в UI (во время insert_row_ui)
            if not name_item or not coord_item or not spinbox:
                continue
                
            new_name = name_item.text()
            old_name = name_item.data(Qt.ItemDataRole.UserRole)
            
            # Если имя изменилось, переименовываем скриншот
            if old_name and old_name != new_name:
                self.save_to_history()
                self.rename_screenshot(old_name, new_name)
                # Обновляем сохраненное старое имя, чтобы не переименовывать повторно
                name_item.setData(Qt.ItemDataRole.UserRole, new_name)
            
            if isinstance(coord_widget, CoordCellWidget):
                x, y = coord_widget.get_values()
                self.coords_table.blockSignals(True)
                coord_item.setText(f"X: {x}, Y: {y}")
                self.coords_table.blockSignals(False)
            else:
                coord_text = coord_item.text()
                nums = re.findall(r'\d+', coord_text)
                x = int(nums[0]) if len(nums) >= 1 else 0
                y = int(nums[1]) if len(nums) >= 2 else 0
            
            target = {
                "name": new_name,
                "x": x,
                "y": y,
                "tolerance": spinbox.value()
            }
            new_list.append(target)
            
        self.coords_list = new_list
        key = f"coords_list_{self.current_coords_tab}"
        self.settings_obj.setValue(key, json.dumps(self.coords_list))
        
        # Обновляем тестовый оверлей, если он включен
        if self.test_overlay and self.test_overlay.isVisible():
            self.test_overlay.update_targets(self.coords_list)

    def move_coord_row(self, source_row, dest_row):
        if source_row == dest_row:
            return
            
        self.save_to_history()
        
        # Переставляем элементы в coords_list
        item = self.coords_list.pop(source_row)
        self.coords_list.insert(dest_row, item)
        
        # Сохраняем новый порядок в QSettings
        key = f"coords_list_{self.current_coords_tab}"
        self.settings_obj.setValue(key, json.dumps(self.coords_list))
        
        # Устанавливаем индекс строки для анимации входа
        self.coords_table.animate_entry_row = dest_row
        
        # Перезагружаем UI
        self.load_coords()
        
        # Выделяем перенесенную строку
        self.coords_table.setCurrentCell(dest_row, 0)
        self.coords_table.selectRow(dest_row)

    def add_coord_row(self):
        self.save_to_history()
        # По умолчанию 10 для кнопок, 0 для остальных (боссы, сундуки, подарки)
        default_tol = 10 if self.current_coords_tab == "buttons" else 0
        new_target = {"name": "Новая точка", "x": 0, "y": 0, "tolerance": default_tol}
        self.coords_list.append(new_target)
        row = self.coords_table.rowCount()
        self.insert_row_ui(row, new_target)
        self.save_coords()

    def detect_coord_auto(self, row):
        region_str = self.settings_obj.value("minimap_region", "", type=str)
        if not region_str:
            QMessageBox.warning(self, "Ошибка", "Сначала определите регион миникарты!")
            return
            
        mark_path = os.path.join(ASSETS_DIR, "mark.png")
        if not os.path.exists(mark_path):
            QMessageBox.warning(self, "Ошибка", f"Файл маркера {mark_path} не найден!")
            return

        # Сворачиваем окно бота
        self.main_window.showMinimized()
        
        # Создаем и запускаем детектор в отдельном потоке
        threshold_str = self.settings_obj.value("match_threshold", "75")
        try:
            threshold = float(threshold_str) / 100.0
        except ValueError:
            threshold = 0.75
            
        timeout_sec = self.timeout_spin.value()
        centering_enabled = self.cb_enable_centering.isChecked()
        centering_offset = (self.interactive_map.original_x, self.interactive_map.original_y)
        
        # Определяем путь для скриншота
        name_item = self.coords_table.item(row, 0)
        name = name_item.text() if name_item else f"unknown_{row}"
        screenshot_path = os.path.join(SCREENSHOTS_DIR, f"{self.current_coords_tab}_{name}.png")
            
        self.detector_thread = AutoDetector(
            region_str, 
            mark_path, 
            threshold, 
            timeout_sec, 
            centering_enabled, 
            centering_offset,
            screenshot_path=screenshot_path
        )
        print(f"DEBUG: Detector thread created: {self.detector_thread}")
        
        def on_finished(pos):
            print(f"DEBUG: on_finished triggered with pos: {pos}")
            # Разворачиваем окно обратно
            self.main_window.showNormal()
            self.main_window.raise_()
            self.main_window.activateWindow()
            
            if pos:
                # Обновляем координаты в списке
                if row < len(self.coords_list):
                    self.save_to_history()
                    self.coords_list[row]["x"] = pos[0]
                    self.coords_list[row]["y"] = pos[1]
                    
                    # Обновляем виджет координат
                    wrapper = self.coords_table.cellWidget(row, 1)
                    coord_widget = get_inner_widget(wrapper)
                    if isinstance(coord_widget, CoordCellWidget):
                        coord_widget.set_values(pos[0], pos[1])
                    
                    # Сохраняем все координаты
                    self.save_coords()
                    
                    # Обновляем текст в ячейке таблицы (2 колонка)
                    coord_item = self.coords_table.item(row, 1)
                    if coord_item:
                        self.coords_table.blockSignals(True)
                        coord_item.setText(f"X: {pos[0]}, Y: {pos[1]}")
                        self.coords_table.blockSignals(False)
                
                if self.test_overlay and self.test_overlay.isVisible():
                    self.test_overlay.update_targets(self.coords_list)
            else:
                QMessageBox.information(self, "Результат", "Маркер не найден на миникарте. Убедитесь, что окно игры не перекрыто.")
            
            # Очищаем поток
            self.detector_thread = None

        self.detector_thread.finished.connect(on_finished)
        print("DEBUG: Signal connected. Starting thread...")
        self.detector_thread.start()

    def delete_coord_row(self, row):
        self.save_to_history()
        self.coords_table.removeRow(row)
        self.save_coords()
        # Обновляем коннекты кнопок, так как индексы строк сдвинулись
        self.refresh_row_buttons()

    def on_tolerance_changed(self, value):
        self.save_to_history()
        self.save_coords()

    def insert_row_ui(self, row, target):
        self.coords_table.blockSignals(True)
        self.coords_table.insertRow(row)
        
        # Гарантируем сброс скрытого состояния и высоты для предотвращения багов с пропаданием строк
        self.coords_table.setRowHidden(row, False)
        
        default_h = self.coords_table.verticalHeader().defaultSectionSize()
        should_animate = (hasattr(self.coords_table, "animate_entry_row") and 
                          self.coords_table.animate_entry_row == row)
                          
        if should_animate:
            self.coords_table.setRowHeight(row, 0)
            self.coords_table.animate_row_height(row, default_h)
            self.coords_table.animate_entry_row = None
        else:
            self.coords_table.setRowHeight(row, default_h)
        
        # 1 колонка: Название
        name_item = QTableWidgetItem(target.get("name", ""))
        name_item.setData(Qt.ItemDataRole.UserRole, target.get("name", ""))
        name_item.setTextAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft)
        name_item.setFlags(name_item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        self.coords_table.setItem(row, 0, name_item)
        
        # 2 колонка: Координаты (подлежащий QTableWidgetItem + красивый встроенный виджет CoordCellWidget)
        coord_cell = QTableWidgetItem(f"X: {target.get('x', 0)}, Y: {target.get('y', 0)}")
        coord_cell.setFlags((coord_cell.flags() & ~Qt.ItemFlag.ItemIsEditable) | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        coord_cell.setTextAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft)
        self.coords_table.setItem(row, 1, coord_cell)
        
        coord_widget = CoordCellWidget(target.get('x', 0), target.get('y', 0), self.save_coords, self.coords_table)
        self.coords_table.setCellWidget(row, 1, CellWrapper(coord_widget))
        
        # 3 колонка: Погрешность (QSpinBox)
        spinbox = QSpinBox()
        spinbox.setRange(0, 500)
        spinbox.setValue(target.get("tolerance", 10))
        spinbox.setStyleSheet("color: #cdd6f4; background-color: #313244; border: none; padding: 2px;")
        spinbox.valueChanged.connect(self.on_tolerance_changed)
        self.coords_table.setCellWidget(row, 2, CellWrapper(spinbox))

        # 4 колонка: Скрин
        btn_snap = QPushButton("🖼")
        btn_snap.setStyleSheet("background-color: #94e2d5; color: #11111b; font-weight: bold; border-radius: 4px; padding: 5px; font-size: 16px;")
        btn_snap.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_snap.clicked.connect(lambda _, r=row: self.show_screenshot(r))
        self.coords_table.setCellWidget(row, 3, CellWrapper(btn_snap))
        
        # 5 колонка: Действие (Опред и Опред+)
        btns_container = QWidget()
        btns_layout = QHBoxLayout(btns_container)
        btns_layout.setContentsMargins(2, 2, 2, 2)
        btns_layout.setSpacing(4)
        
        btn_manual = QPushButton("Опред")
        btn_manual.setStyleSheet("background-color: #89b4fa; color: #11111b; font-weight: bold; padding: 4px; border-radius: 4px;")
        btn_manual.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_manual.clicked.connect(lambda _, r=row: self.start_picking(r))
        
        btn_auto = QPushButton("Опред+")
        btn_auto.setStyleSheet("background-color: #cba6f7; color: #11111b; font-weight: bold; padding: 4px; border-radius: 4px;")
        btn_auto.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_auto.clicked.connect(lambda _, r=row: self.detect_coord_auto(r))
        
        btns_layout.addWidget(btn_manual)
        btns_layout.addWidget(btn_auto)
        self.coords_table.setCellWidget(row, 4, CellWrapper(btns_container))

        # 6 колонка: Удалить
        del_btn = QPushButton("🗑")
        del_btn.setStyleSheet("background-color: #f38ba8; color: #11111b; border-radius: 4px; padding: 5px; font-weight: bold; margin: 2px; font-size: 16px;")
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.clicked.connect(lambda _, r=row: self.delete_coord_row(r))
        self.coords_table.setCellWidget(row, 5, CellWrapper(del_btn))
        
        self.coords_table.blockSignals(False)

    def refresh_row_buttons(self):
        for row in range(self.coords_table.rowCount()):
            # Обновляем кнопку Скрин
            btn_snap = get_inner_widget(self.coords_table.cellWidget(row, 3))
            if btn_snap:
                try: btn_snap.clicked.disconnect()
                except: pass
                btn_snap.clicked.connect(lambda _, r=row: self.show_screenshot(r))

            # Обновляем кнопки в контейнере (Опред и Опред+)
            container = get_inner_widget(self.coords_table.cellWidget(row, 4))
            if container:
                layout = container.layout()
                if layout:
                    btn_man = layout.itemAt(0).widget()
                    btn_auto = layout.itemAt(1).widget()
                    
                    try: btn_man.clicked.disconnect()
                    except: pass
                    btn_man.clicked.connect(lambda _, r=row: self.start_picking(r))
                    
                    try: btn_auto.clicked.disconnect()
                    except: pass
                    btn_auto.clicked.connect(lambda _, r=row: self.detect_coord_auto(r))
            
            # Обновляем кнопку Del
            del_btn = get_inner_widget(self.coords_table.cellWidget(row, 5))
            if del_btn:
                try: del_btn.clicked.disconnect()
                except: pass
                del_btn.clicked.connect(lambda _, r=row: self.delete_coord_row(r))

    def on_map_preview_updated(self, path):
        curr_item = self.maps_list_widget.currentItem()
        if curr_item and curr_item.text() == self.map_recorder.map_name:
            self.on_map_selected()

    def on_map_preview_image_updated(self, qimg):
        curr_item = self.maps_list_widget.currentItem()
        if curr_item and curr_item.text() == self.map_recorder.map_name:
            pixmap = QPixmap.fromImage(qimg)
            self.map_preview_label.setPixmap(pixmap)

    def start_picking(self, row):
        self.current_picking_row = row
        # Сворачиваем главное окно
        self.main_window.showMinimized()
        
        # Создаем прозрачный оверлей на весь экран
        self.picker = PickerOverlay()
        self.picker.coordinate_picked.connect(self.on_coordinate_picked)
        self.picker.show()

    def on_coordinate_picked(self, x, y):
        row = self.current_picking_row
        if 0 <= row < len(self.coords_list):
            self.save_to_history()
            self.coords_list[row]["x"] = x
            self.coords_list[row]["y"] = y
            key = f"coords_list_{self.current_coords_tab}"
            self.settings_obj.setValue(key, json.dumps(self.coords_list))
            
            # Обновляем виджет координат
            wrapper = self.coords_table.cellWidget(row, 1)
            coord_widget = get_inner_widget(wrapper)
            if isinstance(coord_widget, CoordCellWidget):
                coord_widget.set_values(x, y)
            
            # Обновляем UI ячейки
            coord_cell = self.coords_table.item(row, 1)
            if coord_cell:
                self.coords_table.blockSignals(True)
                coord_cell.setText(f"X: {x}, Y: {y}")
                self.coords_table.blockSignals(False)
            
            if self.test_overlay and self.test_overlay.isVisible():
                self.test_overlay.update_targets(self.coords_list)
        
        # Разворачиваем главное окно
        self.main_window.showNormal()
        self.main_window.activateWindow()

    def start_marker_detection(self):
        region_str = self.settings_obj.value("minimap_region", "", type=str)
        if not region_str:
            QMessageBox.warning(self, "Ошибка", "Сначала определите регион миникарты во вкладке 'Карты'!")
            return
            
        try:
            x, y, w, h = map(int, region_str.split(","))
            region = {"top": y, "left": x, "width": w, "height": h}
        except Exception:
            QMessageBox.warning(self, "Ошибка", "Ошибка чтения региона миникарты.")
            return
            
        marker_path = os.path.join(ASSETS_DIR, "mark.png")
        if not os.path.exists(marker_path):
            QMessageBox.warning(self, "Ошибка", f"Не найден файл маркера {marker_path}")
            return
            
        marker_template_full = cv2.imread(marker_path, cv2.IMREAD_UNCHANGED)
        if marker_template_full is None:
            QMessageBox.warning(self, "Ошибка", "Не удалось загрузить маркер.")
            return
            
        # Подготовка маркера без маски (маска делает поиск нестабильным на темном фоне)
        mask = None
        if len(marker_template_full.shape) == 3 and marker_template_full.shape[2] == 4:
            marker_template = cv2.cvtColor(marker_template_full, cv2.COLOR_BGRA2BGR)
        else:
            marker_template = cv2.imread(marker_path, cv2.IMREAD_COLOR)
            
        threshold = self.thresh_slider.value() / 100.0
        timeout_sec = self.timeout_spin.value()
        
        self.main_window.showMinimized()
        
        # Даем время на сворачивание окна
        time.sleep(0.5)
        
        start_time = time.time()
        found = False
        
        with mss.mss() as sct:
            # Учитываем масштаб для региона поиска
            screen = QApplication.primaryScreen()
            scale = screen.devicePixelRatio() if screen else 1.0
            
            phys_region = {
                "top": int(region["top"] * scale),
                "left": int(region["left"] * scale),
                "width": int(region["width"] * scale),
                "height": int(region["height"] * scale)
            }
            while time.time() - start_time < timeout_sec:
                try:
                    sct_img = sct.grab(phys_region)
                    img = np.array(sct_img, dtype=np.uint8)
                    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                except Exception:
                    time.sleep(0.1)
                    continue
                
                if mask is not None:
                    result = cv2.matchTemplate(img_rgb, marker_template, cv2.TM_CCOEFF_NORMED, mask=mask)
                else:
                    result = cv2.matchTemplate(img_rgb, marker_template, cv2.TM_CCOEFF_NORMED)
                    
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                
                if max_val >= threshold:
                    found = True
                    # Глобальные координаты на экране
                    screen_x = region["left"] + max_loc[0]
                    screen_y = region["top"] + max_loc[1]
                    
                    marker_h, marker_w = marker_template.shape[:2]
                    
                    # Делаем скриншот зоны 100x100 вокруг найденного маркера
                    center_x_local = max_loc[0] + marker_w // 2
                    center_y_local = max_loc[1] + marker_h // 2
                    
                    # Рассчитываем область для скриншота
                    snap_w, snap_h = 100, 100
                    snap_left = max(0, center_x_local - snap_w // 2)
                    snap_top = max(0, center_y_local - snap_h // 2)
                    snap_right = min(img.shape[1], snap_left + snap_w)
                    snap_bottom = min(img.shape[0], snap_top + snap_h)
                    
                    # Вырезаем область
                    snapshot = img_rgb[snap_top:snap_bottom, snap_left:snap_right].copy()
                    
                    # Рисуем рамку вокруг найденного маркера
                    marker_box_left = max_loc[0] - snap_left
                    marker_box_top = max_loc[1] - snap_top
                    cv2.rectangle(snapshot, (marker_box_left, marker_box_top), 
                                 (marker_box_left + marker_w, marker_box_top + marker_h), 
                                 (0, 255, 0), 2)
                                 
                    # Рисуем перекрестие в центре
                    cx = center_x_local - snap_left
                    cy = center_y_local - snap_top
                    cv2.drawMarker(snapshot, (cx, cy), (0, 0, 255), cv2.MARKER_CROSS, 10, 2)
                    
                    # Добавляем смещение (если включено центрирование)
                    if self.cb_enable_centering.isChecked():
                        # self.interactive_map.original_x уже находится в физических пикселях маркера,
                        # поэтому переводить умножением на scale не требуется.
                        target_cx = marker_box_left + int(self.interactive_map.original_x)
                        target_cy = marker_box_top + int(self.interactive_map.original_y)
                        cv2.circle(snapshot, (target_cx, target_cy), 3, (255, 0, 0), -1)
                    
                    self.show_marker_snapshot(snapshot, max_val)
                    break
                    
                time.sleep(0.2)
                
        # Сначала восстанавливаем окно
        self.main_window.showNormal()
        self.main_window.raise_()
        self.main_window.activateWindow()
        
        if not found:
            # Стилизованное уведомление об ошибке
            msg = QMessageBox(self)
            msg.setWindowTitle("Результат")
            msg.setText(f"Маркер не найден за {timeout_sec} сек.")
            msg.setStyleSheet("color: black;")
            msg.exec()
            
    def show_marker_snapshot(self, img_bgr, confidence):
        # Восстанавливаем окно ПЕРЕД показом диалога, чтобы он вылетел поверх
        self.main_window.showNormal()
        self.main_window.raise_()
        self.main_window.activateWindow()
        # Конвертируем BGR в RGB для Qt
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = img_rgb.shape
        bytes_per_line = ch * w
        q_img = QImage(img_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(q_img)
        
        # Увеличиваем в 2-3 раза для наглядности
        scaled_pixmap = pixmap.scaled(w * 3, h * 3, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Маркер найден!")
        layout = QVBoxLayout(dialog)
        
        lbl_img = QLabel()
        lbl_img.setPixmap(scaled_pixmap)
        lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        lbl_info = QLabel(f"Уверенность: {confidence * 100:.1f}%\n"
                         f"Зеленая рамка - маркер\n"
                         f"Красный крест - геом. центр\n"
                         f"Синяя точка - ваше смещение")
        lbl_info.setStyleSheet("font-size: 14px; font-weight: bold; padding: 10px;")
        lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        btn_ok = QPushButton("Отлично")
        btn_ok.setStyleSheet("background-color: #a6e3a1; color: black; font-weight: bold; padding: 5px;")
        btn_ok.clicked.connect(dialog.accept)
        
        layout.addWidget(lbl_img)
        layout.addWidget(lbl_info)
        layout.addWidget(btn_ok)
        
        dialog.exec()

    def toggle_test_overlay(self, checked):
        if checked:
            # Собираем все координаты со всех вкладок
            all_targets = []
            tab_keys = ["buttons", "bosses", "chests", "gifts"]
            for key in tab_keys:
                json_data = self.settings_obj.value(f"coords_list_{key}", "[]", type=str)
                try:
                    all_targets.extend(json.loads(json_data))
                except:
                    pass
            
            color = QColor(self.settings_obj.value("test_crosshair_color", "#ff0000"))
            length = self.settings_obj.value("test_crosshair_length", 15, type=int)
            
            if not self.test_overlay:
                self.test_overlay = TestOverlay(all_targets)
            
            self.test_overlay.update_targets(all_targets, color, length)
            self.test_overlay.show()
        else:
            if self.test_overlay:
                self.test_overlay.hide()

    def change_category(self, index):
        self.content_stack.setCurrentIndex(index)

    def go_back(self):
        self.main_window.show_main_page()

    # --- МЕТОДЫ ВКЛАДКИ КАРТЫ ---
    def load_maps_list(self):
        self.maps_list_widget.clear()
        if hasattr(self, 'rec_map_combo'):
            self.rec_map_combo.clear()
        maps_json = self.settings_obj.value("maps_list", "[]", type=str)
        try:
            self.maps = json.loads(maps_json)
        except json.JSONDecodeError:
            self.maps = []
            
        for map_name in self.maps:
            self.maps_list_widget.addItem(QListWidgetItem(map_name))
            if hasattr(self, 'rec_map_combo'):
                self.rec_map_combo.addItem(map_name)
            
    def add_map(self):
        name, ok = QInputDialog.getText(self, "Новая карта", "Введите название карты:")
        if ok and name and name not in self.maps:
            self.maps.append(name)
            self.settings_obj.setValue("maps_list", json.dumps(self.maps))
            self.load_maps_list()
            
    def delete_map(self):
        curr_item = self.maps_list_widget.currentItem()
        if curr_item:
            name = curr_item.text()
            reply = QMessageBox.question(self, "Удаление", f"Удалить карту '{name}' и ВСЕ её файлы?", 
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                # 1. Удаляем папку физически
                map_dir = os.path.join(ASSETS_DIR, "maps", name)
                if os.path.exists(map_dir):
                    try:
                        shutil.rmtree(map_dir)
                        print(f"DEBUG: Папка {map_dir} удалена")
                    except Exception as e:
                        QMessageBox.warning(self, "Ошибка удаления", 
                                             f"Не удалось удалить файлы карты '{name}'.\n"
                                             f"Пожалуйста, убедитесь, что картинки карты не открыты в сторонних программах (например, в Просмотре фотографий Windows)!\n\n"
                                             f"Детали ошибки: {e}")
                        return # Прерываем выполнение, оставляя карту в списке для повторной попытки

                # 2. Удаляем из настроек только при успешном физическом удалении
                if name in self.maps:
                    self.maps.remove(name)
                self.settings_obj.setValue("maps_list", json.dumps(self.maps))
                self.load_maps_list()
                self.map_preview_label.setText("Выберите карту для предпросмотра")
                self.open_editor_btn.hide()
                
    def on_map_selected(self):
        curr_item = self.maps_list_widget.currentItem()
        if not curr_item:
            return
            
        name = curr_item.text()
        map_dir = os.path.join(ASSETS_DIR, "maps", name)
        walkability_path = os.path.join(map_dir, "walkability.png")
        region_info_path = os.path.join(map_dir, "region.json")
        
        print(f"DEBUG: on_map_selected for '{name}'")
        print(f"DEBUG: Path walkability: {os.path.exists(walkability_path)}")
        print(f"DEBUG: Path region: {os.path.exists(region_info_path)}")

        if os.path.exists(walkability_path) and os.path.exists(region_info_path):
            try:
                # 1. Загружаем регион
                with open(region_info_path, "r") as f:
                    region = json.load(f)
                
                # Показываем старые офсеты в интерфейсе
                ox = region.get("offset_x", 0)
                oy = region.get("offset_y", 0)
                self.shift_was_val.setText(f"{ox}, {oy}")
                # Сразу ставим их в поля "Стало" для удобной правки
                self.shift_x_spin.setValue(ox)
                self.shift_y_spin.setValue(oy)
                print(f"DEBUG: Region loaded: {region}")
                
                # 2. Загружаем глобальную карту
                with open(walkability_path, "rb") as f:
                    chunk = np.frombuffer(f.read(), dtype=np.uint8)
                    full_map = cv2.imdecode(chunk, cv2.IMREAD_COLOR)
                
                if full_map is not None:
                    print(f"DEBUG: Map loaded, size: {full_map.shape}")
                    # Учитываем масштаб
                    screen = QApplication.primaryScreen()
                    scale = screen.devicePixelRatio() if screen else 1.0
                    print(f"DEBUG: Current scale: {scale}")
                    
                    # 3. Переводим в физические пиксели
                    px = int(region["x"] * scale)
                    py = int(region["y"] * scale)
                    pw = int(region["w"] * scale)
                    ph = int(region["h"] * scale)
                    print(f"DEBUG: Target crop phys: x={px}, y={py}, w={pw}, h={ph}")
                    
                    # Проверяем границы
                    y2 = min(full_map.shape[0], py + ph)
                    x2 = min(full_map.shape[1], px + pw)
                    
                    # Если масштаб 1.0 не сработал (например, картинка уже в логических), 
                    # или если физические координаты выходят за рамки слишком сильно
                    if px >= full_map.shape[1] or py >= full_map.shape[0]:
                        print("DEBUG: Физические координаты вне картинки, пробуем логические...")
                        px, py, pw, ph = region["x"], region["y"], region["w"], region["h"]
                        y2 = min(full_map.shape[0], py + ph)
                        x2 = min(full_map.shape[1], px + pw)

                    cropped = full_map[py:y2, px:x2]
                    print(f"DEBUG: Cropped size: {cropped.shape if cropped is not None else 'None'}")
                    
                    if cropped is not None and cropped.size > 0:
                        # Конвертируем в QPixmap
                        height, width, channel = cropped.shape
                        bytesPerLine = 3 * width
                        qImg = QImage(cropped.data.tobytes(), width, height, bytesPerLine, QImage.Format.Format_BGR888)
                        pixmap = QPixmap.fromImage(qImg)
                        
                        if not pixmap.isNull():
                            scaled_pixmap = pixmap.scaled(300, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                            self.map_preview_label.setPixmap(scaled_pixmap)
                            self.open_editor_btn.show()
                            print("DEBUG: Preview updated successfully")
                            return
                        else:
                            print("DEBUG: Pixmap is null!")
            except Exception as e:
                print(f"DEBUG: Ошибка превью: {e}")
                import traceback
                traceback.print_exc()

        self.map_preview_label.setText("Нет данных проходимости.\nЗапишите маршрут.")
        self.open_editor_btn.hide()
            
    def shift_map_paths(self):
        curr_item = self.maps_list_widget.currentItem()
        if not curr_item:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите карту в списке!")
            return
            
        name = curr_item.text()
        map_dir = os.path.join(ASSETS_DIR, "maps", name)
        walkability_path = os.path.join(map_dir, "walkability.png")
        region_info_path = os.path.join(map_dir, "region.json")
        
        if not os.path.exists(walkability_path) or not os.path.exists(region_info_path):
            QMessageBox.warning(self, "Ошибка", "Данные карты не найдены!")
            return

        try:
            # 1. Загружаем старые данные
            with open(region_info_path, "r") as f:
                region = json.load(f)
            
            old_ox = region.get("offset_x", 0)
            old_oy = region.get("offset_y", 0)
            
            # 2. Получаем новые данные из полей ввода
            new_ox = self.shift_x_spin.value()
            new_oy = self.shift_y_spin.value()
            
            if old_ox == new_ox and old_oy == new_oy:
                QMessageBox.information(self, "Инфо", "Координаты не изменились. Смещение не требуется.")
                return
                
            # 3. Вычисляем разницу в ЛОГИЧЕСКИХ пикселях
            # Если новый офсет больше старого (сдвинули центр вправо/вниз), 
            # то нарисованные ПУТИ на картинке должны сдвинуться в ту же сторону.
            dx_logical = new_ox - old_ox
            dy_logical = new_oy - old_oy
            
            # 4. Переводим в ФИЗИЧЕСКИЕ пиксели (для картинки)
            screen = QApplication.primaryScreen()
            scale = screen.devicePixelRatio() if screen else 1.0
            dx_phys = float(dx_logical * scale)
            dy_phys = float(dy_logical * scale)
            
            # 5. Загружаем и сдвигаем картинку
            with open(walkability_path, "rb") as f:
                chunk = np.frombuffer(f.read(), dtype=np.uint8)
                img = cv2.imdecode(chunk, cv2.IMREAD_COLOR)
            
            if img is not None:
                # Матрица афинного преобразования для сдвига
                M = np.float32([[1, 0, dx_phys], [0, 1, dy_phys]])
                shifted_img = cv2.warpAffine(img, M, (img.shape[1], img.shape[0]))
                
                # 6. Сохраняем результат
                is_success, buffer = cv2.imencode(".png", shifted_img)
                if is_success:
                    with open(walkability_path, "wb") as f:
                        f.write(buffer)
                
                # 7. Обновляем region.json новыми офсетами
                region["offset_x"] = new_ox
                region["offset_y"] = new_oy
                with open(region_info_path, "w") as f:
                    json.dump(region, f)
                
                # 8. Обновляем UI
                self.on_map_selected()
                QMessageBox.information(self, "Успех", f"Пути успешно смещены на ({dx_logical}, {dy_logical}) пикселей.")
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сместить пути: {e}")

    def open_map_editor(self):
        curr_item = self.maps_list_widget.currentItem()
        if curr_item:
            name = curr_item.text()
            map_path = os.path.join(ASSETS_DIR, "maps", name, "walkability.png")
            if os.path.exists(map_path):
                os.startfile(map_path)
                
    def run_test_move(self):
        # 1. Проверяем, выбрана ли карта и есть ли данные проходимости
        curr_item = self.maps_list_widget.currentItem()
        if not curr_item:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите карту в списке!")
            return
            
        map_name = curr_item.text()
        map_path = os.path.join(ASSETS_DIR, "maps", map_name, "walkability.png")
        if not os.path.exists(map_path):
            QMessageBox.warning(self, "Ошибка", f"Для карты '{map_name}' нет данных проходимости! Сначала запишите маршрут.")
            return

        # 2. Проверяем координаты цели
        coords_text = self.test_coords_input.text()
        nums = re.findall(r'\d+', coords_text)
        if len(nums) < 2:
            QMessageBox.warning(self, "Ошибка", "Введите корректные координаты X и Y (например: 100, 200)!")
            return
            
        target_pos = (int(nums[0]), int(nums[1]))
        
        # 3. Ищем настройки джойстика
        joy_settings = self.find_joystick_settings()
        if not joy_settings:
            QMessageBox.warning(self, "Ошибка", "Не найдены настройки джойстика! Добавьте в таблицу точку с названием 'Управление'.")
            return

        # 4. Регион миникарты
        region_str = self.settings_obj.value("minimap_region", "", type=str)
        if not region_str:
            QMessageBox.warning(self, "Ошибка", "Регион миникарты не задан!")
            return
            
        try:
            x_reg, y_reg, w_reg, h_reg = map(int, region_str.split(","))
            region = {"top": y_reg, "left": x_reg, "width": w_reg, "height": h_reg}
        except:
            return

        # Сворачиваем окно
        self.main_window.showMinimized()
        
        # Запускаем поток движения
        screen = QApplication.primaryScreen()
        scale = screen.devicePixelRatio() if screen else 1.0
        marker_path = os.path.join(ASSETS_DIR, "mark.png")
        threshold = float(self.settings_obj.value("match_threshold", "75")) / 100.0
        
        scan_interval = self.scan_interval_spin.value()
        target_tolerance = self.target_tolerance_spin.value()
        wall_offset = self.nav_offset_spin.value()
        wp_straight = self.wp_straight_spin.value()
        wp_turn = self.wp_turn_spin.value()
        early_stop = self.early_stop_spin.value()
        lookahead_straight = self.lookahead_straight_spin.value()
        lookahead_turn_min = self.lookahead_turn_min_spin.value()
        stop_turn_pause = self.stop_turn_pause_spin.value()
        
        self.move_thread = TestMoveThread(
            target_pos, joy_settings, region, scale, marker_path, threshold,
            self.cb_enable_centering.isChecked(),
            (self.interactive_map.original_x, self.interactive_map.original_y),
            scan_interval, target_tolerance, map_path, wall_offset, wp_straight, wp_turn, early_stop,
            self.cb_save_debug_map.isChecked(),
            lookahead_straight=lookahead_straight,
            lookahead_turn_min=lookahead_turn_min,
            stop_turn_pause=stop_turn_pause
        )
        
        def on_move_finished():
            self.main_window.showNormal()
            self.main_window.raise_()
            self.main_window.activateWindow()
            
        def on_move_error(msg):
            QMessageBox.warning(self, "Ошибка навигации", msg)
            
        self.move_thread.finished.connect(on_move_finished)
        self.move_thread.error_occurred.connect(on_move_error)
        self.move_thread.start()

    def run_passive_test_move(self):
        # 1. Проверяем, выбрана ли карта и есть ли данные проходимости
        curr_item = self.maps_list_widget.currentItem()
        if not curr_item:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите карту в списке!")
            return
            
        map_name = curr_item.text()
        map_path = os.path.join(ASSETS_DIR, "maps", map_name, "walkability.png")
        if not os.path.exists(map_path):
            QMessageBox.warning(self, "Ошибка", f"Для карты '{map_name}' нет данных проходимости!")
            return

        # 2. Проверяем координаты цели (опционально)
        coords_text = self.test_coords_input.text().strip()
        target_pos = None
        if coords_text:
            nums = re.findall(r'\d+', coords_text)
            if len(nums) >= 2:
                target_pos = (int(nums[0]), int(nums[1]))
        
        # 3. Ищем настройки джойстика
        joy_settings = self.find_joystick_settings()
        if not joy_settings:
            QMessageBox.warning(self, "Ошибка", "Не найдены настройки джойстика! Добавьте в таблицу точку с названием 'Управление'.")
            return

        # 4. Регион миникарты
        region_str = self.settings_obj.value("minimap_region", "", type=str)
        if not region_str:
            QMessageBox.warning(self, "Ошибка", "Регион миникарты не задан!")
            return
            
        try:
            x_reg, y_reg, w_reg, h_reg = map(int, region_str.split(","))
            region = {"top": y_reg, "left": x_reg, "width": w_reg, "height": h_reg}
        except:
            return

        # Сворачиваем окно
        self.main_window.showMinimized()
        
        # Запускаем поток движения в пассивном режиме
        screen = QApplication.primaryScreen()
        scale = screen.devicePixelRatio() if screen else 1.0
        marker_path = os.path.join(ASSETS_DIR, "mark.png")
        threshold = float(self.settings_obj.value("match_threshold", "75")) / 100.0
        
        scan_interval = self.scan_interval_spin.value()
        target_tolerance = self.target_tolerance_spin.value()
        wall_offset = self.nav_offset_spin.value()
        wp_straight = self.wp_straight_spin.value()
        wp_turn = self.wp_turn_spin.value()
        early_stop = self.early_stop_spin.value()
        lookahead_straight = self.lookahead_straight_spin.value()
        lookahead_turn_min = self.lookahead_turn_min_spin.value()
        stop_turn_pause = self.stop_turn_pause_spin.value()
        
        self.move_thread = TestMoveThread(
            target_pos, joy_settings, region, scale, marker_path, threshold,
            self.cb_enable_centering.isChecked(),
            (self.interactive_map.original_x, self.interactive_map.original_y),
            scan_interval, target_tolerance, map_path, wall_offset, wp_straight, wp_turn, early_stop,
            save_debug_map=True,
            passive_mode=True,
            lookahead_straight=lookahead_straight,
            lookahead_turn_min=lookahead_turn_min,
            stop_turn_pause=stop_turn_pause
        )
        
        def on_move_finished():
            self.main_window.showNormal()
            self.main_window.raise_()
            self.main_window.activateWindow()
            
        def on_move_error(msg):
            QMessageBox.warning(self, "Ошибка навигации", msg)
            
        self.move_thread.finished.connect(on_move_finished)
        self.move_thread.error_occurred.connect(on_move_error)
        self.move_thread.start()

    def find_joystick_settings(self):
        """Ищет строку 'Управление' во всех категориях координат."""
        categories = ["buttons", "bosses", "chests", "gifts"]
        for cat in categories:
            key = f"coords_list_{cat}"
            coords_json = self.settings_obj.value(key, "[]", type=str)
            try:
                coords_list = json.loads(coords_json)
                for item in coords_list:
                    if item.get("name", "").strip().lower() == "управление":
                        return {
                            "x": item.get("x", 0),
                            "y": item.get("y", 0),
                            "radius": item.get("tolerance", 50)
                        }
            except:
                continue
        return None

    def get_joystick_drag_point(self, cur_x, cur_y, tar_x, tar_y, joy_x, joy_y, joy_r):
        """
        Вычисляет точку, в которую нужно потянуть мышь из центра джойстика (joy_x, joy_y),
        чтобы персонаж бежал из (cur_x, cur_y) в (tar_x, tar_y).
        """
        # Вектор движения
        dx = tar_x - cur_x
        dy = tar_y - cur_y
        
        # Угол в радианах
        angle = math.atan2(dy, dx)
        
        # Проекция вектора на джойстик с учетом радиуса
        drag_x = joy_x + math.cos(angle) * joy_r
        drag_y = joy_y + math.sin(angle) * joy_r
        
        return int(drag_x), int(drag_y)

    def start_region_picking(self):
        self.main_window.showMinimized()
        self.region_picker = RegionPickerOverlay()
        self.region_picker.region_picked.connect(self.on_region_picked)
        self.region_picker.show()
        
    def on_region_picked(self, x, y, w, h):
        region_str = f"{x},{y},{w},{h}"
        self.settings_obj.setValue("minimap_region", region_str)
        if hasattr(self, 'region_val_label'):
            self.region_val_label.setText(region_str)
        
        time.sleep(0.1)
        
        map_name = ""
        try:
            curr_item = self.maps_list_widget.currentItem()
            if curr_item:
                map_name = curr_item.text()
            elif hasattr(self, 'rec_map_combo') and self.rec_map_combo.currentText():
                map_name = self.rec_map_combo.currentText()
        except Exception as e:
            print(f"DEBUG: Ошибка при получении имени карты: {e}")
            
        if map_name:
            try:
                screen = QApplication.primaryScreen()
                scale = screen.devicePixelRatio() if screen else 1.0
                
                # Координаты всего экрана (первого монитора)
                with mss.mss() as sct:
                    monitor = sct.monitors[1] # Основной монитор
                    full_sct = sct.grab(monitor)
                    
                    map_dir = os.path.join(ASSETS_DIR, "maps", map_name)
                    os.makedirs(map_dir, exist_ok=True)
                    
                    original_map_path = os.path.join(map_dir, "map_original.png")
                    walkability_path = os.path.join(map_dir, "walkability.png")
                    region_info_path = os.path.join(map_dir, "region.json")
                    
                    # 1. Сохраняем ПОЛНЫЙ скриншот экрана как оригинал
                    img_full = np.array(full_sct)
                    img_rgb = cv2.cvtColor(img_full, cv2.COLOR_BGRA2BGR)
                    
                    is_success, buffer = cv2.imencode(".png", img_rgb)
                    if is_success:
                        with open(original_map_path, "wb") as f:
                            f.write(buffer)
                    
                    # 2. Инициализируем walkability.png (Глобальный черный холст)
                    if not os.path.exists(walkability_path):
                        black_canvas = np.zeros((img_rgb.shape[0], img_rgb.shape[1], 3), dtype=np.uint8)
                        is_success_bw, bw_buffer = cv2.imencode(".png", black_canvas)
                        if is_success_bw:
                            with open(walkability_path, "wb") as f:
                                f.write(bw_buffer)
                    
                    # 3. Сохраняем координаты региона и офсеты в JSON
                    ox = self.interactive_map.original_x if hasattr(self, 'interactive_map') else 0
                    oy = self.interactive_map.original_y if hasattr(self, 'interactive_map') else 0
                    
                    region_data = {
                        "x": x, "y": y, "w": w, "h": h, 
                        "screen_w": img_rgb.shape[1], "screen_h": img_rgb.shape[0],
                        "scale": scale,
                        "offset_x": ox, "offset_y": oy
                    }
                    with open(region_info_path, "w") as f:
                        json.dump(region_data, f)
                    
                    print(f"DEBUG: Global Canvas инициализирован для {map_name}")
                    self.on_map_selected()
            except Exception as e:
                print(f"Ошибка Global Canvas: {e}")

        self.main_window.showNormal()
        self.main_window.activateWindow()
        QMessageBox.information(self, "Успех", "Глобальная карта инициализирована. Регион сохранен.")

        self.main_window.showNormal()
        self.main_window.activateWindow()
        
        if map_name:
            QMessageBox.information(self, "Успех", f"Регион задан. Старые маршруты перенесены.")
        else:
            QMessageBox.warning(self, "Инфо", "Регион сохранен.")

    def pick_char_color(self):
        current_hex = self.settings_obj.value("rec_char_color", "#00ff00", type=str)
        color = QColorDialog.getColor(QColor(current_hex), self, "Выберите цвет персонажа")
        if color.isValid():
            new_hex = color.name()
            self.settings_obj.setValue("rec_char_color", new_hex)
            self.char_color_btn.setStyleSheet(f"background-color: {new_hex}; border-radius: 4px; border: 1px solid #313244;")

    def start_map_recording(self):
        curr_item = self.maps_list_widget.currentItem()
        if not curr_item:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите карту в списке 'Менеджер карт'!")
            return
            
        map_name = curr_item.text()
        interval_ms = self.rec_interval_spin.value()
        brush_radius = self.rec_brush_spin.value()
        
        # Получаем цвет из настроек (как RGB для PIL)
        char_color_hex = self.settings_obj.value("rec_char_color", "#00ff00", type=str)
        qcolor = QColor(char_color_hex)
        char_color_rgb = (qcolor.red(), qcolor.green(), qcolor.blue())
        
        # Передаем настройки центрирования
        centering_enabled = getattr(self, 'cb_enable_centering', None) is not None and self.cb_enable_centering.isChecked()
        offset_x = self.interactive_map.original_x if hasattr(self, 'interactive_map') else 0
        offset_y = self.interactive_map.original_y if hasattr(self, 'interactive_map') else 0
        
        is_reverse = self.rec_reverse_btn.isChecked()
        
        if self.map_recorder.start_recording(map_name, interval_ms, centering_enabled, (offset_x, offset_y), brush_radius, char_color_rgb, is_reverse):
            self.rec_start_btn.setText("● REC...")
            self.rec_start_btn.setStyleSheet("background-color: #f38ba8; color: #11111b; font-weight: bold; padding: 5px; border: 2px solid white;")
            self.rec_start_btn.setEnabled(False)
            self.rec_stop_btn.setEnabled(True)
            self.rec_map_combo.setEnabled(False)
        else:
            QMessageBox.warning(self, "Ошибка", "Ошибка старта записи! Убедитесь, что выделен регион миникарты и файл маркера существует.")

    def stop_map_recording(self):
        if self.map_recorder.is_running:
            self.map_recorder.stop_recording()
            self.rec_start_btn.setText("▶ Запись")
            self.rec_start_btn.setStyleSheet("background-color: #f38ba8; color: #11111b; font-weight: bold; padding: 5px;")
            self.rec_start_btn.setEnabled(True)
            self.rec_stop_btn.setEnabled(False)
            self.rec_map_combo.setEnabled(True)
            self.on_map_selected()

    def emergency_stop(self):
        print("DEBUG: Emergency stop triggered!")
        import pyautogui
        pyautogui.mouseUp()
        
        # 1. Останавливаем поток движения
        if hasattr(self, 'move_thread') and self.move_thread and self.move_thread.isRunning():
            print("DEBUG: Saving debug image before terminating move_thread...")
            self.move_thread.save_debug_image()
            print("DEBUG: Terminating move_thread...")
            self.move_thread.terminate()
            self.move_thread.wait()
            self.move_thread = None
            
        # 2. Останавливаем поток автодетектора
        if hasattr(self, 'detector_thread') and self.detector_thread and self.detector_thread.isRunning():
            print("DEBUG: Terminating detector_thread...")
            self.detector_thread.terminate()
            self.detector_thread.wait()
            self.detector_thread = None
            
        # 3. Останавливаем запись карты
        if hasattr(self, 'map_recorder') and self.map_recorder and self.map_recorder.is_running:
            print("DEBUG: Stopping map recording...")
            self.stop_map_recording()
            
        # 4. Восстанавливаем окно бота
        self.main_window.showNormal()
        self.main_window.raise_()
        self.main_window.activateWindow()
        
        # 5. Показываем стилизованное уведомление
        QMessageBox.information(self, "Экстренная остановка", "Все фоновые процессы бота (тестовый бег, автодетект, запись карты) принудительно остановлены по нажатию Ctrl 5 раз!")
