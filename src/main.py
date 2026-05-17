import sys
import os
import ctypes
from PyQt6.QtWidgets import QApplication

# Включаем поддержку DPI awareness до создания QApplication
try:
    # Для Windows 8.1 и новее
    ctypes.windll.shcore.SetProcessDpiAwareness(1) # 1 = Process_System_DPI_Aware
except Exception:
    try:
        # Для более старых версий Windows
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import traceback
import datetime

# Определяем пути
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, '..'))
LOG_FILE = os.path.join(ROOT_DIR, "bot.log")

class Logger(object):
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.log = open(filename, "a", encoding="utf-8")
        # Сообщение о начале сессии
        start_msg = f"\n{'='*50}\n[SESSION STARTED] {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{'='*50}\n"
        self.write(start_msg)

    def write(self, message):
        # Вывод в консоль (оригинальный)
        self.terminal.write(message)
        
        # Вывод в файл с таймстампом для каждой новой строки
        if message and message != '\n':
            # Если это не просто перенос строки, добавляем время
            timestamp = datetime.datetime.now().strftime("[%H:%M:%S] ")
            # Очищаем сообщение от лишних переносов в начале/конце для красоты лога
            clean_msg = message.strip()
            if clean_msg:
                self.log.write(f"{timestamp}{clean_msg}\n")
        
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

# Перенаправляем вывод
sys.stdout = Logger(LOG_FILE)
sys.stderr = sys.stdout

# Добавляем корневую директорию проекта в sys.path, чтобы корректно работали импорты
sys.path.insert(0, ROOT_DIR)

from src.gui.main_window import MainWindow

def exception_hook(exctype, value, tb):
    with open("crash.log", "w", encoding="utf-8") as f:
        traceback.print_exception(exctype, value, tb, file=f)
    sys.__excepthook__(exctype, value, tb)

sys.excepthook = exception_hook

def main():
    app = QApplication(sys.argv)
    
    # Загрузка темной темы (QSS)
    style_path = os.path.join(os.path.dirname(__file__), "gui", "styles.qss")
    if os.path.exists(style_path):
        with open(style_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    else:
        print(f"Warning: Stylesheet not found at {style_path}")
            
    window = MainWindow()
    window.show()
    
    # Корректное завершение работы
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
