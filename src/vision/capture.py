import mss
import numpy as np
from src.tools.window_utils import get_window_rect

class ScreenCapturer:
    def __init__(self):
        self.sct = mss.mss()
        
    def capture_window(self, window_name):
        """Захватывает экран по координатам переданного окна эмулятора."""
        rect = get_window_rect(window_name)
        if not rect:
            return None # Окно не найдено
            
        left, top, right, bottom = rect
        
        # Защита от свернутых окон (у них координаты часто отрицательные или нулевая ширина/высота)
        if right - left <= 0 or bottom - top <= 0 or left < -10000:
            return None
            
        monitor = {
            "top": top,
            "left": left,
            "width": right - left,
            "height": bottom - top
        }
        
        # Захват кадра (очень быстро)
        sct_img = self.sct.grab(monitor)
        
        # Конвертация в формат numpy array (удобно для OpenCV)
        # sct_img имеет формат BGRA
        img = np.array(sct_img)
        return img
