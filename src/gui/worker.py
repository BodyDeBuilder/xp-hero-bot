from PyQt6.QtCore import QThread, pyqtSignal
import time
from src.vision.capture import ScreenCapturer

class BotWorker(QThread):
    # Сигналы для общения с главным потоком (Main Thread)
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    
    def __init__(self, target_window_name=None):
        super().__init__()
        self.is_running = True
        self.target_window_name = target_window_name
        self.capturer = ScreenCapturer()

    def set_target_window(self, window_name):
        self.target_window_name = window_name

    def stop(self):
        """Останавливает бесконечный цикл воркера."""
        self.is_running = False

    def run(self):
        """Этот метод выполняется в отдельном фоновом потоке при вызове start()"""
        self.log_signal.emit("Запуск воркера...")
        
        if not self.target_window_name:
            self.error_signal.emit("Окно эмулятора не выбрано!")
            return

        self.log_signal.emit(f"Привязка к окну: {self.target_window_name}")
        
        step_counter = 1
        
        # Основной цикл бота
        while self.is_running:
            # 1. Захват экрана
            frame = self.capturer.capture_window(self.target_window_name)
            
            if frame is None:
                self.error_signal.emit("Не удалось захватить экран. Окно свернуто или закрыто?")
                time.sleep(2) # Пауза перед повторной попыткой
                continue
                
            # 2. Здесь будет логика обработки кадра (Computer Vision)
            # Временно мы просто симулируем работу
            self.log_signal.emit(f"Шаг {step_counter}: Захват экрана успешен ({frame.shape})")
            
            # Симуляция бурной деятельности бота
            time.sleep(1.5)
            step_counter += 1
            
        self.log_signal.emit("Воркер остановлен.")
