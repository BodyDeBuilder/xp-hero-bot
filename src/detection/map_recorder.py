import os
import cv2
import numpy as np
import mss
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication
from PIL import Image, ImageDraw

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "assets")

class MapRecorder(QThread):
    preview_updated = pyqtSignal(str) # Путь к обновленному файлу карты
    
    def __init__(self, settings_obj):
        super().__init__()
        self.settings_obj = settings_obj
        self.is_running = False
        self.map_name = ""
        self.marker_path = os.path.join(ASSETS_DIR, "mark.png")
        self.marker_template = None
        self.walkability_img = None
        self.walkability_draw = None
        self.map_dir = ""
        self.walkability_path = ""
        
        # Загружаем маркер
        if os.path.exists(self.marker_path):
            self.load_marker()
            
    def load_marker(self):
        marker_template_full = cv2.imread(self.marker_path, cv2.IMREAD_UNCHANGED)
        if marker_template_full is not None:
            if len(marker_template_full.shape) == 4:
                self.marker_template = cv2.cvtColor(marker_template_full, cv2.COLOR_BGRA2BGR)
                alpha_channel = marker_template_full[:, :, 3]
                _, self.marker_mask = cv2.threshold(alpha_channel, 127, 255, cv2.THRESH_BINARY)
            else:
                self.marker_template = cv2.imread(self.marker_path, cv2.IMREAD_COLOR)
                self.marker_mask = None
        else:
            self.marker_template = None
            self.marker_mask = None
            
    def start_recording(self, map_name, interval_ms=500, centering_enabled=False, centering_offset=(0, 0), brush_radius=4, char_color=(0, 255, 0), is_reverse=False):
        if self.marker_template is None:
            print(f"Маркер не найден: {self.marker_path}")
            return False
            
        self.map_name = map_name
        self.interval_ms = interval_ms
        self.centering_enabled = centering_enabled
        self.centering_offset = centering_offset
        self.brush_radius = brush_radius
        self.char_color = char_color
        self.is_reverse = is_reverse
        self.last_pos = None # Для рисования линий
        
        self.map_dir = os.path.join(ASSETS_DIR, "maps", map_name)
        os.makedirs(self.map_dir, exist_ok=True)
        
        self.walkability_path = os.path.join(self.map_dir, "walkability.png")
        
        # Читаем регион из настроек
        region_str = self.settings_obj.value("minimap_region", "", type=str)
        if not region_str:
            print("Регион миникарты не задан!")
            return False
            
        try:
            x, y, w, h = map(int, region_str.split(","))
            self.region = {"top": y, "left": x, "width": w, "height": h}
        except Exception:
            return False
            
        # Подготовка изображения проходимости
        if os.path.exists(self.walkability_path):
            self.walkability_img = Image.open(self.walkability_path).convert("RGB")
            # Проверяем, соответствует ли размер текущему региону (логическому)
            if self.walkability_img.size != (self.region["width"], self.region["height"]):
                # Если регион изменился, создаем новую черную карту
                self.walkability_img = Image.new("RGB", (self.region["width"], self.region["height"]), "black")
        else:
            self.walkability_img = Image.new("RGB", (self.region["width"], self.region["height"]), "black")
            
        self.walkability_draw = ImageDraw.Draw(self.walkability_img)
        
        # Порог уверенности
        try:
            self.threshold = float(self.settings_obj.value("match_threshold", "75", type=str)) / 100.0
        except ValueError:
            self.threshold = 0.75
        
        self.is_running = True
        self.start()
        return True
        
    def stop_recording(self):
        self.is_running = False
        self.wait()
        
    def run(self):
        with mss.mss() as sct:
            # Учитываем масштаб
            screen = QApplication.primaryScreen()
            scale = screen.devicePixelRatio() if screen else 1.0
            
            phys_region = {
                "top": int(self.region["top"] * scale),
                "left": int(self.region["left"] * scale),
                "width": int(self.region["width"] * scale),
                "height": int(self.region["height"] * scale)
            }
            
            # Кисть для рисования
            radius = self.brush_radius
            
            while self.is_running:
                try:
                    # 1. Скриншот (физический регион)
                    sct_img = sct.grab(phys_region)
                    img = np.array(sct_img)
                    
                    # Убираем альфа-канал
                    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                    
                    # 2. Поиск маркера
                    if getattr(self, 'marker_mask', None) is not None:
                        result = cv2.matchTemplate(img_rgb, self.marker_template, cv2.TM_CCORR_NORMED, mask=self.marker_mask)
                    else:
                        result = cv2.matchTemplate(img_rgb, self.marker_template, cv2.TM_CCORR_NORMED)
                    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                    
                    if max_val >= self.threshold:
                        # Маркер найден. max_loc - координаты в ФИЗИЧЕСКИХ пикселях.
                        # Переводим в ЛОГИЧЕСКИЕ (чтобы совпадало с размером картинки)
                        found_x_logical = max_loc[0] / scale
                        found_y_logical = max_loc[1] / scale
                        
                        if self.centering_enabled:
                            # Добавляем смещение перекрестья (оно уже логическое)
                            center_x = found_x_logical + self.centering_offset[0]
                            center_y = found_y_logical + self.centering_offset[1]
                        else:
                            # Если без центрирования - берем центр самого маркера
                            marker_h, marker_w = self.marker_template.shape[:2]
                            center_x = found_x_logical + (marker_w / scale) / 2
                            center_y = found_y_logical + (marker_h / scale) / 2
                            
                        # Текущая точка для отрисовки
                        current_pos = (int(center_x), int(center_y))
                        
                        # Цвет закраски: белый для дорог, черный для препятствий (реверс)
                        paint_color = "black" if self.is_reverse else "white"

                        # Рисуем строго выбранным цветом на основной карте
                        if self.last_pos is not None:
                            # Рисуем толстую линию от прошлой точки к текущей
                            self.walkability_draw.line([self.last_pos, current_pos], fill=paint_color, width=radius*2)
                        
                        self.walkability_draw.ellipse(
                            (current_pos[0] - radius, current_pos[1] - radius, current_pos[0] + radius, current_pos[1] + radius), 
                            fill=paint_color
                        )
                        
                        self.last_pos = current_pos
                        
                        # Сохраняем промежуточный результат и обновляем UI
                        self.walkability_img.save(self.walkability_path)
                        self.preview_updated.emit(os.path.abspath(self.walkability_path))
                        
                except Exception as e:
                    print(f"Ошибка записи карты: {e}")
                    
                self.msleep(self.interval_ms)
