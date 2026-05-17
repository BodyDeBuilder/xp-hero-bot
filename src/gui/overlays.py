from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush

class PickerOverlay(QWidget):
    coordinate_picked = pyqtSignal(int, int)

    def __init__(self):
        super().__init__()
        # Делаем окно полноэкранным, прозрачным и без рамок
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Устанавливаем курсор прицел
        self.setCursor(Qt.CursorShape.CrossCursor)

    def showEvent(self, event):
        # Растягиваем на весь экран
        if QApplication.primaryScreen():
            screen_geometry = QApplication.primaryScreen().geometry()
            self.setGeometry(screen_geometry)
        super().showEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        # Полупрозрачная заливка, чтобы было видно, что включен режим пикера (едва заметно)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 30))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            x = int(event.globalPosition().x())
            y = int(event.globalPosition().y())
            self.coordinate_picked.emit(x, y)
            self.close()

    def keyPressEvent(self, event):
        # Выход по Esc
        if event.key() == Qt.Key.Key_Escape:
            self.close()


class TestOverlay(QWidget):
    def __init__(self, targets):
        super().__init__()
        self.targets = targets if targets is not None else []
        self.crosshair_color = QColor(255, 0, 0, 200)
        self.crosshair_length = 15

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def update_targets(self, targets, color=None, length=None):
        self.targets = targets if targets is not None else []
        if color: self.crosshair_color = color
        if length is not None: self.crosshair_length = length
        self.update()

    def showEvent(self, event):
        if QApplication.primaryScreen():
            screen_geometry = QApplication.primaryScreen().geometry()
            self.setGeometry(screen_geometry)
        super().showEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Настройка пера для кругов и перекрестий
        painter.setPen(QPen(self.crosshair_color, 2))
        # Для заливки кругов используем тот же цвет, но прозрачнее
        fill_color = QColor(self.crosshair_color)
        fill_color.setAlpha(60)
        painter.setBrush(QBrush(fill_color))
        
        for target in self.targets:
            x = int(target.get("x", 0))
            y = int(target.get("y", 0))
            tolerance = int(target.get("tolerance", 0))
            
            # 1. Рисуем зону погрешности (круг)
            if tolerance > 0:
                painter.drawEllipse(x - tolerance, y - tolerance, tolerance * 2, tolerance * 2)
            else:
                painter.drawEllipse(x - 3, y - 3, 6, 6)
                
            # 2. Рисуем перекрестье
            L = self.crosshair_length
            if L > 0:
                # Горизонтальная линия
                painter.drawLine(x - L, y, x + L, y)
                # Вертикальная линия
                painter.drawLine(x, y - L, x, y + L)

class RegionPickerOverlay(QWidget):
    region_picked = pyqtSignal(int, int, int, int) # x, y, width, height

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.start_point = None
        self.current_point = None

    def showEvent(self, event):
        if QApplication.primaryScreen():
            screen_geometry = QApplication.primaryScreen().geometry()
            self.setGeometry(screen_geometry)
        super().showEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80)) # Затенение экрана
        
        if self.start_point and self.current_point:
            # Рисуем выделенную область
            x = min(self.start_point.x(), self.current_point.x())
            y = min(self.start_point.y(), self.current_point.y())
            w = abs(self.start_point.x() - self.current_point.x())
            h = abs(self.start_point.y() - self.current_point.y())
            
            # Делаем выделенную область прозрачной
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(x, y, w, h, Qt.GlobalColor.transparent)
            
            # Возвращаем режим и рисуем рамку
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            pen = QPen(QColor(0, 255, 0))
            pen.setWidth(2)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(x, y, w, h)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_point = event.globalPosition().toPoint()
            self.current_point = self.start_point
            self.update()

    def mouseMoveEvent(self, event):
        if self.start_point:
            self.current_point = event.globalPosition().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.start_point:
            self.current_point = event.globalPosition().toPoint()
            
            x = min(self.start_point.x(), self.current_point.x())
            y = min(self.start_point.y(), self.current_point.y())
            w = abs(self.start_point.x() - self.current_point.x())
            h = abs(self.start_point.y() - self.current_point.y())
            
            # Скрываем оверлей СРАЗУ, чтобы он не попал на скриншот
            self.hide()
            QApplication.processEvents()
            
            # Отправляем только если область больше 10x10 пикселей
            if w > 10 and h > 10:
                self.region_picked.emit(x, y, w, h)
                
            self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
