# test_validator.py
from tools.slide_validator import SlideValidator

# Тест 1: Валидный слайд
valid_slide = {
    "background": {"type": "solid", "color": "$primary"},
    "elements": [
        {"elementType": "text", "bounds": [100, 100, 800, 200],
         "content": {"text": "Заголовок", "style": "$title"}},
        {"elementType": "icon", "iconName": "star", "bounds": [1600, 800, 120, 120]}
    ]
}
print("✅ Валидный слайд:", SlideValidator.validate(valid_slide)[0])

# Тест 2: Пересечение элементов
overlap_slide = {
    "background": {"type": "solid", "color": "$primary"},
    "elements": [
        {"elementType": "text", "bounds": [100, 100, 500, 200],
         "content": {"text": "Текст", "style": "$body"}},
        {"elementType": "icon", "bounds": [400, 150, 200, 200], "iconName": "star"}
    ]
}
is_valid, errors = SlideValidator.validate(overlap_slide)
print("❌ Пересечение:", is_valid, "→", errors[0] if errors else "OK")

# Тест 3: Некорректный цвет
bad_color_slide = {
    "background": {"type": "solid", "color": "green"},  # ❌ без $
    "elements": [{"elementType": "text", "bounds": [100,100,200,50],
                  "content": {"text": "Hi", "style": "$body"}}]
}
is_valid, errors = SlideValidator.validate(bad_color_slide)
print("❌ Цвет:", is_valid, "→", errors[0] if errors else "OK")