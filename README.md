# Kimi PPTD Agent v2.0

Веб-сервис на FastAPI для генерации и конвертации презентаций.

## Архитектура

```
kimi_agent_service/
├── main.py                  # FastAPI приложение
├── converter.py             # Конвертер .pptd → .pptx (не изменялся)
├── icon_manager.py          # Новый модуль управления иконками
├── requirements.txt
├── README.md
├── projects/                # Автосоздаётся для результатов
├── icons/                   # Библиотека Phosphor (уже у вас)
│   ├── SVGs/
│   │   ├── bold/
│   │   ├── duotone/
│   │   ├── fill/
│   │   ├── light/
│   │   ├── regular/
│   │   └── thin/
│   ├── SVGs Flat/           # Аналогичная структура
│   ├── PNGs/
│   └── Fonts/
├── templates/
│   ├── index.html           # Генерация
│   └── converter.html       # Конвертер
└── static/
    ├── css/
    │   └── style.css        # Полностью светлый интерфейс
    └── js/
        ├── main.js
        └── converter.js
```

## Установка

```bash
pip install -r requirements.txt
```

Для SVG→EMF конвертации (опционально):
```bash
# Windows: скачайте Inkscape
# Linux: sudo apt install inkscape
# macOS: brew install inkscape
```

## Запуск

```bash
python main.py
```

## Использование

### 1. Генерация презентации (заглушка)
- Откройте http://localhost:8000/
- Введите тему, выберите параметры
- Нажмите "Сгенерировать"

### 2. Конвертация .pptd → .pptx
- Перейдите на http://localhost:8000/converter
- Загрузите ZIP с .pptd + pages/ + images/
- Получите .pptx (FullHD 1920×1080)

### 3. Библиотека иконок
- http://localhost:8000/icons — просмотр и поиск иконок Phosphor

## Интеграция с GigaChat агентом

В `main.py` в эндпоинте `/api/generate` замените заглушку:

```python
# TODO: Ваш агент здесь
from your_agent import GigaChatAgent
agent = GigaChatAgent()
result = agent.generate(request.topic, request.slides_count, request.style)
# Сохраните .pptd и .page файлы в proj_dir
```

## Настройки

### Разрешение
В `converter.py`:
```python
SLIDE_WIDTH_PX = 1920   # или 3840 для 4K
SLIDE_HEIGHT_PX = 1080  # или 2160 для 4K
```

### Цвета темы UI
В `main.py`:
```python
THEME_COLORS = {
    "primary": "#1E3330",
    "accent": "#C9892E",
    ...
}
```
