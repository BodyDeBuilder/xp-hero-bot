import sys
import os
from PyQt6.QtWidgets import QApplication

# Добавляем корневую директорию в sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.gui.overlays import TestOverlay

if __name__ == '__main__':
    app = QApplication(sys.path)
    overlay = TestOverlay(100, 100, 20)
    overlay.show()
    sys.exit(app.exec())
