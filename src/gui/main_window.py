import sys
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, 
    QLabel, QListWidget, QListWidgetItem, QTabWidget, 
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QAbstractItemView, QComboBox, QSplitter, QSizePolicy, QStackedWidget
)
from PyQt6.QtCore import Qt, QSettings
from src.tools.window_utils import get_open_windows
from src.gui.worker import BotWorker
from src.gui.settings_page import SettingsPage

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("XP Hero Bot - Control Panel")
        self.resize(1200, 800)

        # Главный виджет (Stacked Widget для переключения страниц)
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)
        
        # --- Страница 1: Главный экран ---
        self.main_page = QWidget()
        main_vbox = QVBoxLayout(self.main_page)
        main_vbox.setContentsMargins(10, 10, 10, 10)
        
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_vbox.addWidget(self.main_splitter)

        self.setup_left_panel()
        self.setup_right_panel()

        self.main_splitter.setSizes([300, 900])
        
        self.stacked_widget.addWidget(self.main_page)
        
        # --- Страница 2: Настройки ---
        self.settings_page = SettingsPage(self)
        self.stacked_widget.addWidget(self.settings_page)

        # Инициализация воркера
        self.worker = None

        # Заполнение тестовыми данными
        self.populate_dummy_data()
        
        # Загрузка сохраненных настроек
        self.load_settings()

    def show_settings_page(self):
        self.stacked_widget.setCurrentIndex(1)
        
    def show_main_page(self):
        self.stacked_widget.setCurrentIndex(0)

    def setup_left_panel(self):
        self.left_panel_widget = QWidget()
        self.left_panel = QVBoxLayout(self.left_panel_widget)
        self.left_panel.setContentsMargins(0, 0, 0, 0)
        self.main_splitter.addWidget(self.left_panel_widget)

        # === Очередность действий ===
        title = QLabel("Очередность действий")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 5px;")
        self.left_panel.addWidget(title)

        self.action_list = QListWidget()
        self.action_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.left_panel.addWidget(self.action_list)

        self.demo_step_btn = QPushButton("Сделать шаг (Демо)")
        self.demo_step_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.demo_step_btn.setProperty("class", "DemoButton")
        self.demo_step_btn.clicked.connect(self.complete_current_step)
        self.left_panel.addWidget(self.demo_step_btn)

        # Растягивающееся пространство, чтобы прижать панель управления к низу
        self.left_panel.addStretch()

        # === Панель управления ===
        controls_layout = QVBoxLayout()
        
        # Выбор окна
        window_select_layout = QHBoxLayout()
        self.window_combo = QComboBox()
        self.window_combo.setStyleSheet("padding: 5px; font-size: 14px; background-color: #181825; color: #cdd6f4; border: 1px solid #313244;")
        self.window_combo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.window_combo.setMinimumWidth(100)
        
        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setFixedSize(32, 32)
        self.refresh_btn.setStyleSheet("background-color: #313244; color: white; border-radius: 4px;")
        self.refresh_btn.clicked.connect(self.refresh_windows)
        
        window_select_layout.addWidget(QLabel("Окно эмулятора:"))
        window_select_layout.addWidget(self.window_combo, stretch=1)
        window_select_layout.addWidget(self.refresh_btn)
        
        controls_layout.addLayout(window_select_layout)
        
        # Кнопка Старт / Стоп
        self.start_btn = QPushButton("Старт")
        self.start_btn.setProperty("class", "StartButton")
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.clicked.connect(self.toggle_bot)
        controls_layout.addWidget(self.start_btn)
        
        self.left_panel.addLayout(controls_layout)
        
        # Загружаем список окон при старте
        self.refresh_windows()
                
    def refresh_windows(self):
        current_selection = self.window_combo.currentText()
        self.window_combo.clear()
        windows = get_open_windows()
        self.window_combo.addItems(windows)
        # Пытаемся восстановить выбор
        index = self.window_combo.findText(current_selection)
        if index >= 0:
            self.window_combo.setCurrentIndex(index)

    def toggle_bot(self):
        if self.worker is None or not self.worker.isRunning():
            # Запуск бота
            target_window = self.window_combo.currentText()
            self.worker = BotWorker(target_window)
            self.worker.log_signal.connect(self.add_action_step)
            self.worker.error_signal.connect(self.add_action_step)
            self.worker.finished.connect(self.on_worker_finished)
            
            self.worker.start()
            
            # Меняем вид кнопки
            self.start_btn.setText("Стоп")
            self.start_btn.setProperty("class", "StopButton")
            self.start_btn.style().unpolish(self.start_btn)
            self.start_btn.style().polish(self.start_btn)
        else:
            # Остановка бота
            self.worker.stop()
            self.start_btn.setText("Останавливаем...")
            self.start_btn.setEnabled(False)

    def on_worker_finished(self):
        self.start_btn.setText("Старт")
        self.start_btn.setProperty("class", "StartButton")
        self.start_btn.setEnabled(True)
        self.start_btn.style().unpolish(self.start_btn)
        self.start_btn.style().polish(self.start_btn)

    def setup_right_panel(self):
        self.right_panel_widget = QWidget()
        self.right_panel = QVBoxLayout(self.right_panel_widget)
        self.right_panel.setContentsMargins(0, 0, 0, 0)
        self.main_splitter.addWidget(self.right_panel_widget)

        # Заголовок и кнопка настроек
        header_layout = QHBoxLayout()
        title = QLabel("Задачи")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        
        # Кнопка закрепления окна
        self.pin_btn = QPushButton("📌")
        self.pin_btn.setFixedSize(32, 32)
        self.pin_btn.setCheckable(True)
        self.pin_btn.setStyleSheet("""
            QPushButton { background-color: #313244; color: white; border-radius: 4px; font-size: 16px; }
            QPushButton:checked { background-color: #a6e3a1; color: #11111b; }
        """)
        self.pin_btn.setToolTip("Закрепить поверх других окон")
        self.pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pin_btn.clicked.connect(self.toggle_stay_on_top)
        
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setFixedSize(32, 32)
        self.settings_btn.setStyleSheet("background-color: #313244; color: white; border-radius: 4px; font-size: 18px;")
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.clicked.connect(self.show_settings_page)
        
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self.pin_btn)
        header_layout.addSpacing(5)
        header_layout.addWidget(self.settings_btn)
        header_layout.setContentsMargins(0, 0, 0, 5)
        
        self.right_panel.addLayout(header_layout)

        self.tabs = QTabWidget()
        self.right_panel.addWidget(self.tabs)

        self.tab_bosses = self.create_table_tab("bosses")
        self.tab_chests = self.create_table_tab("chests")
        self.tab_gifts = self.create_table_tab("gifts")
        self.tab_other = self.create_table_tab("other")

        self.tabs.addTab(self.tab_bosses, "Боссы")
        self.tabs.addTab(self.tab_chests, "Сундуки")
        self.tabs.addTab(self.tab_gifts, "Подарки")
        self.tabs.addTab(self.tab_other, "Другое")
        
        # Сохраняем список всех таблиц для синхронизации и других нужд
        self.tables = [self.tab_bosses, self.tab_chests, self.tab_gifts, self.tab_other]
        
        # Подключаем синхронизацию ширины столбцов
        for table in self.tables:
            table.horizontalHeader().sectionResized.connect(self.sync_column_widths)

    def toggle_stay_on_top(self, checked):
        if checked:
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)
        self.show() # Необходимо вызвать show() после изменения флагов

    def sync_column_widths(self, logicalIndex, oldSize, newSize):
        """Синхронизирует ширину колонки во всех таблицах, если она была изменена в одной из них."""
        for table in self.tables:
            header = table.horizontalHeader()
            if header.sectionSize(logicalIndex) != newSize:
                # Отключаем сигналы временно, чтобы не вызвать бесконечную рекурсию
                header.blockSignals(True)
                header.resizeSection(logicalIndex, newSize)
                header.blockSignals(False)

    def create_table_tab(self, object_name):
        table = QTableWidget(0, 5)
        # Устанавливаем objectName, чтобы отличать таблицы при сохранении настроек
        table.setObjectName(f"table_{object_name}")
        table.setHorizontalHeaderLabels(["Название", "Мир", "Награда", "Таймер", ""])
        
        # Меняем режим изменения размера на Interactive
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        
        # Последняя колонка фиксированная (для корзины)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(4, 50)
        
        # Разрешаем тянуть за заголовки
        table.horizontalHeader().setStretchLastSection(False)
        
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        return table

    def add_table_row(self, table: QTableWidget, name: str, world: str, reward: str, timer: str):
        row = table.rowCount()
        table.insertRow(row)
        
        table.setItem(row, 0, QTableWidgetItem(name))
        table.setItem(row, 1, QTableWidgetItem(world))
        table.setItem(row, 2, QTableWidgetItem(reward))
        table.setItem(row, 3, QTableWidgetItem(timer))
        
        delete_btn = QPushButton("🗑")
        delete_btn.setProperty("class", "DeleteButton")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.clicked.connect(lambda _, r=row, t=table: self.delete_row(t, r))
        
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.addWidget(delete_btn)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)
        
        table.setCellWidget(row, 4, widget)

    def delete_row(self, table: QTableWidget, row_to_delete: int):
        for row in range(table.rowCount()):
            widget = table.cellWidget(row, 4)
            if widget:
                btn = widget.findChild(QPushButton)
                if btn == self.sender():
                    table.removeRow(row)
                    break

    def add_action_step(self, text: str):
        item = QListWidgetItem(text)
        self.action_list.addItem(item)
        self.update_action_list_highlight()
        self.action_list.scrollToBottom()

    def complete_current_step(self):
        if self.action_list.count() > 0:
            self.action_list.takeItem(0)
            self.update_action_list_highlight()

    def update_action_list_highlight(self):
        for i in range(self.action_list.count()):
            item = self.action_list.item(i)
            if i == 0:
                item.setSelected(True)
                if not item.text().startswith("▶ "):
                    item.setText("▶ " + item.text())
            else:
                item.setSelected(False)
                if item.text().startswith("▶ "):
                    item.setText(item.text()[2:])

    def populate_dummy_data(self):
        steps = [
            "Инициализация эмулятора...",
            "Поиск окна игры",
            "Сбор ежедневных наград"
        ]
        for step in steps:
            self.add_action_step(step)

        self.add_table_row(self.tab_bosses, "Огненный демон", "Вулкан", "Меч пламени", "05:00")
        self.add_table_row(self.tab_bosses, "Ледяной дракон", "Северный пик", "Кристалл льда", "12:30")
        self.add_table_row(self.tab_chests, "Золотой сундук", "Лес теней", "Золото x1000", "00:00 (Готов)")
        self.add_table_row(self.tab_gifts, "Ежедневный подарок", "Главное меню", "Кристаллы x50", "00:00 (Готов)")

    # === СОХРАНЕНИЕ НАСТРОЕК ===
    def load_settings(self):
        settings = QSettings("XPHero", "BotUI")
        
        # Восстановление геометрии и состояния окна
        geometry = settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
            
        window_state = settings.value("windowState")
        if window_state:
            self.restoreState(window_state)
            
        # Восстановление размеров сплиттера
        splitter_state = settings.value("mainSplitter")
        if splitter_state:
            self.main_splitter.restoreState(splitter_state)
            
        # Восстановление размеров колонок в таблицах
        for table in [self.tab_bosses, self.tab_chests, self.tab_gifts, self.tab_other]:
            header_state = settings.value(f"headerState_{table.objectName()}")
            if header_state:
                table.horizontalHeader().restoreState(header_state)

    def closeEvent(self, event):
        """Метод вызывается при закрытии окна крестиком."""
        # Если бот работает, останавливаем его корректно
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()
            
        # Сохранение настроек интерфейса
        settings = QSettings("XPHero", "BotUI")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
        settings.setValue("mainSplitter", self.main_splitter.saveState())
        
        # Сохраняем состояние каждой таблицы
        for table in [self.tab_bosses, self.tab_chests, self.tab_gifts, self.tab_other]:
            settings.setValue(f"headerState_{table.objectName()}", table.horizontalHeader().saveState())
            
        super().closeEvent(event)
