# Архитектура проекта XP Hero Bot

Данный документ описывает модульную архитектуру визуального бота для игры "XP Hero", работающего через Android-эмулятор. Бот основан исключительно на Computer Vision и не взаимодействует с памятью игры.

## Файловая структура

```text
xp_hero_bot/
│
├── src/                      # Исходный код бота
│   ├── main.py               # Точка входа в приложение
│   ├── vision/               # Vision Module (cv2, yolo, ocr)
│   │   ├── capture.py        # Захват экрана (mss)
│   │   ├── detector.py       # Детекция объектов (YOLOv8/11)
│   │   └── ocr.py            # Распознавание текста (EasyOCR)
│   │
│   ├── navigation/           # Navigation & Mapping Module
│   │   ├── map_engine.py     # Обработка карты коллизий
│   │   └── pathfinder.py     # Алгоритм A* (pathfinding)
│   │
│   ├── logic/                # Logic & State Machine
│   │   ├── fsm.py            # Реализация состояний бота (IDLE, COMBAT, etc.)
│   │   └── tasks/            # Отдельные сценарии поведения
│   │
│   ├── control/              # Модуль эмуляции ввода
│   │   ├── emulator_adb.py   # Отправка команд через ADB (pure-python-adb)
│   │   └── emulator_gui.py   # Резервное управление мышью (PyAutoGUI)
│   │
│   ├── gui/                  # GUI & Scheduler Module (PyQt6)
│   │   ├── main_window.py    # Главное окно (Main Thread)
│   │   ├── worker.py         # Поток выполнения бота (QThread)
│   │   └── scheduler.py      # Планировщик задач (APScheduler)
│   │
│   └── tools/                # Вспомогательные утилиты
│       └── mapper.py         # Mapper Utility (утилита снятия координат)
│
├── config/                   # Конфигурации и данные
│   ├── settings.json         # Глобальные настройки бота
│   └── locations.json        # База данных координат и точек интереса
│
├── models/                   # Модели машинного обучения
│   ├── yolo_weights.pt       # Модели для детекции YOLO
│   └── maps/                 # Карты и маски коллизий
│       └── collision_mask.png
│
├── requirements.txt          # Зависимости Python
└── ARCHITECTURE.md           # Этот файл (описание архитектуры)
```

## Форматы хранения данных (JSON)

### `config/settings.json`

Файл отвечает за глобальные настройки работы бота, эмулятора и алгоритмов машинного зрения. 

```json
{
  "emulator": {
    "window_name": "LDPlayer",
    "use_adb": true,
    "adb_port": 5555,
    "resolution": {"width": 1280, "height": 720}
  },
  "vision": {
    "confidence_threshold": 0.7,
    "ocr_lang": ["en", "ru"],
    "yolo_model_path": "../models/yolo_weights.pt"
  },
  "scheduler": {
    "enable_daily_quests": true,
    "farm_duration_minutes": 120
  }
}
```

### `config/locations.json`

Файл базы данных координат (сборник "точек" на экране эмулятора). Генерируется и пополняется через встроенную программу-помощник (`Mapper Utility`). 

```json
{
  "buttons": {
    "auto_battle": {"x": 1150, "y": 650, "type": "static"},
    "close_menu": {"x": 1200, "y": 50, "type": "static"}
  },
  "world_objects": {
    "boss_spawn": {"x": 500, "y": 400, "type": "map_coord"}
  },
  "ui_elements": {
    "health_bar": {
      "region": {"x1": 100, "y1": 50, "x2": 400, "y2": 70},
      "type": "dynamic_read"
    }
  }
}
```

- **type**: 
  - `static` (постоянная координата на экране), 
  - `map_coord` (координата на игровой карте, требующая навигации), 
  - `dynamic_read` (область/регион для чтения характеристик через OCR или OpenCV).
