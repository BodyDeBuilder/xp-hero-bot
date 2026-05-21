import os
import cv2
import numpy as np
import mss
import json
import time
import io
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication
from PIL import Image, ImageDraw

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "assets")

class MapRecorder(QThread):
    preview_updated = pyqtSignal(str) # Путь к обновленному файлу карты
    preview_image_updated = pyqtSignal(QImage) # Новое: сигнал с готовым QImage для real-time превью в памяти
    
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
            if len(marker_template_full.shape) == 3 and marker_template_full.shape[2] == 4:
                self.marker_template = cv2.cvtColor(marker_template_full, cv2.COLOR_BGRA2BGR)
            else:
                self.marker_template = cv2.imread(self.marker_path, cv2.IMREAD_COLOR)
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
        self.last_pos = None 
        
        self.map_dir = os.path.join(ASSETS_DIR, "maps", map_name)
        os.makedirs(self.map_dir, exist_ok=True)
        
        self.walkability_path = os.path.join(self.map_dir, "walkability.png")
        
        region_str = self.settings_obj.value("minimap_region", "", type=str)
        if not region_str:
            print("Регион миникарты не задан!")
            return False
            
        try:
            x, y, w, h = map(int, region_str.split(","))
            self.region = {"top": y, "left": x, "width": w, "height": h}
        except Exception:
            return False
            
        # ГЛОБАЛЬНЫЙ ХОЛСТ: Определяем физический размер экрана
        screen = QApplication.primaryScreen()
        scale = screen.devicePixelRatio() if screen else 1.0
        geom = screen.geometry()
        phys_w = int(geom.width() * scale)
        phys_h = int(geom.height() * scale)

        if os.path.exists(self.walkability_path):
            self.walkability_img = Image.open(self.walkability_path).convert("RGB")
            if self.walkability_img.size != (phys_w, phys_h):
                self.walkability_img = Image.new("RGB", (phys_w, phys_h), "black")
        else:
            self.walkability_img = Image.new("RGB", (phys_w, phys_h), "black")
            
        self.walkability_draw = ImageDraw.Draw(self.walkability_img)
        
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
        region_info_path = os.path.join(self.map_dir, "region.json")
        try:
            with open(region_info_path, "r") as f:
                reg_data = json.load(f)
        except:
            print("ОШИБКА: Файл region.json не найден. Запись невозможна.")
            return

        with mss.mss() as sct:
            screen = QApplication.primaryScreen()
            scale = screen.devicePixelRatio() if screen else 1.0
            
            phys_region = {
                "top": int(self.region["top"] * scale),
                "left": int(self.region["left"] * scale),
                "width": int(self.region["width"] * scale),
                "height": int(self.region["height"] * scale)
            }
            
            radius = self.brush_radius
            
            # Настройки real-time обновления превью и слежения
            last_preview_time = 0.0
            last_known_pos = None
            hero_matched_now = False
            consecutive_lost_frames = 0
            
            while self.is_running:
                try:
                    sct_img = sct.grab(phys_region)
                    img = np.array(sct_img)
                    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                    
                    if getattr(self, 'marker_mask', None) is not None:
                        result = cv2.matchTemplate(img_rgb, self.marker_template, cv2.TM_CCOEFF_NORMED, mask=self.marker_mask)
                    else:
                        result = cv2.matchTemplate(img_rgb, self.marker_template, cv2.TM_CCOEFF_NORMED)
                    
                    _, max_val, _, max_loc = cv2.minMaxLoc(result)
                    
                    hero_matched_now = False
                    if max_val >= self.threshold:
                        hero_matched_now = True
                        consecutive_lost_frames = 0
                        phys_region_x = int(self.region["left"] * scale)
                        phys_region_y = int(self.region["top"] * scale)
                        marker_h_phys, marker_w_phys = self.marker_template.shape[:2]
                        
                        if self.centering_enabled:
                            found_x_phys = max_loc[0] + self.centering_offset[0]
                            found_y_phys = max_loc[1] + self.centering_offset[1]
                        else:
                            found_x_phys = max_loc[0] + marker_w_phys / 2
                            found_y_phys = max_loc[1] + marker_h_phys / 2
                            
                        global_x_phys = int(phys_region_x + found_x_phys)
                        global_y_phys = int(phys_region_y + found_y_phys)
                        
                        current_pos = (global_x_phys, global_y_phys)
                        last_known_pos = current_pos
                        paint_color = "black" if self.is_reverse else "white"

                        try:
                            # Вычисляем толщину линии: 
                            # Если радиус 0 -> ширина 1
                            # Если радиус 1 -> ширина 3 (центр + 1 с каждой стороны)
                            # Учитываем DPI (scale)
                            line_width = int((self.brush_radius * 2 + 1) * scale)
                            if line_width < 1: line_width = 1
                            
                            # Для круга (закраска точки)
                            r_phys = int(self.brush_radius * scale)
                            
                            if self.last_pos is not None:
                                self.walkability_draw.line([self.last_pos, current_pos], fill=paint_color, width=line_width)
                            
                            self.walkability_draw.ellipse(
                                (current_pos[0] - r_phys, current_pos[1] - r_phys, 
                                 current_pos[0] + r_phys, current_pos[1] + r_phys), 
                                fill=paint_color
                            )
                        except Exception: pass
                        
                        self.last_pos = current_pos
                    else:
                        consecutive_lost_frames += 1
                        # Если герой потерян более чем на 5 кадров (~50мс при 10мс интервале),
                        # сбрасываем last_pos, чтобы избежать рисования диагональных линий-пролагов.
                        if consecutive_lost_frames > 5:
                            self.last_pos = None

                    # Обновляем превью в памяти (без дискового I/O) с частотой ~10 FPS
                    current_time = time.time()
                    if current_time - last_preview_time >= 0.1:
                        last_preview_time = current_time
                        try:
                            rx = reg_data.get("x", 0)
                            ry = reg_data.get("y", 0)
                            rw = reg_data.get("w", 0)
                            rh = reg_data.get("h", 0)
                            
                            px = int(rx * scale)
                            py = int(ry * scale)
                            pw = int(rw * scale)
                            ph = int(rh * scale)
                            
                            y2 = min(self.walkability_img.height, py + ph)
                            x2 = min(self.walkability_img.width, px + pw)
                            
                            if px < self.walkability_img.width and py < self.walkability_img.height:
                                cropped = self.walkability_img.crop((px, py, x2, y2))
                                
                                # Создаем временную копию для наложения маркера
                                preview_img = cropped.copy()
                                if last_known_pos is not None:
                                    hero_x = last_known_pos[0] - px
                                    hero_y = last_known_pos[1] - py
                                    
                                    # Отрисовываем положение героя только если оно попадает в границы кропа
                                    if 0 <= hero_x < (x2 - px) and 0 <= hero_y < (y2 - py):
                                        draw_preview = ImageDraw.Draw(preview_img)
                                        r_dot = int(5 * scale)
                                        # Цвет: Яркий красный если найден сейчас, или оранжевый если потерян
                                        dot_color = (255, 0, 0) if hero_matched_now else (255, 165, 0)
                                        draw_preview.ellipse(
                                            (hero_x - r_dot, hero_y - r_dot, hero_x + r_dot, hero_y + r_dot),
                                            fill=dot_color,
                                            outline="white" if hero_matched_now else "gray"
                                        )
                                
                                preview_img.thumbnail((300, 300))
                                preview_rgb = preview_img.convert("RGB")
                                
                                # Сверхбезопасная конвертация через BMP в памяти
                                byte_io = io.BytesIO()
                                preview_rgb.save(byte_io, format="BMP")
                                qimg = QImage.fromData(byte_io.getvalue())
                                if not qimg.isNull():
                                    self.preview_image_updated.emit(qimg)
                        except Exception as e:
                            print(f"Ошибка периодического обновления превью: {e}")
                        
                except Exception as e:
                    print(f"Ошибка записи карты: {e}")
                    
                self.msleep(self.interval_ms)

            # Финальное сохранение при остановке записи
            try:
                self.walkability_img.save(self.walkability_path)
                self.preview_updated.emit(os.path.abspath(self.walkability_path))
                print("DEBUG: Финальное сохранение карты выполнено.")
            except Exception as e:
                print(f"Ошибка финального сохранения карты: {e}")
