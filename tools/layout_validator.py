"""
Инструмент проверки макета слайда.
Проверяет пересечения элементов, выход за границы, минимальное наполнение.
Возвращает список замечаний.
"""

from typing import List, Dict, Any, Tuple
import yaml

def _parse_coords(bounds: list) -> Tuple[float, float, float, float]:
    x, y, w, h = bounds
    return x, y, x + w, y + h

def check_intersection(b1, b2) -> bool:
    x1_min, y1_min, x1_max, y1_max = _parse_coords(b1)
    x2_min, y2_min, x2_max, y2_max = _parse_coords(b2)
    if x1_min >= x2_max or x1_max <= x2_min or y1_min >= y2_max or y1_max <= y2_min:
        return False
    return True

def validate_page(page_yaml: Dict[str, Any], min_elements: int = 2) -> List[str]:
    """
    Возвращает список замечаний. Пустой список – всё хорошо.
    """
    warnings = []
    elements = page_yaml.get("elements", [])
    if len(elements) < min_elements:
        warnings.append(f"Слишком мало элементов (нужно минимум {min_elements})")

    # Собираем bounds всех элементов
    bounds_list = []
    for i, el in enumerate(elements):
        if "bounds" not in el:
            warnings.append(f"Элемент {i} ({el.get('elementType', '?')}) не имеет bounds")
            continue
        b = el["bounds"]
        if len(b) != 4:
            warnings.append(f"Неверный bounds у элемента {i}")
            continue
        x, y, w, h = b
        if w <= 0 or h <= 0:
            warnings.append(f"Нулевой размер у элемента {i}")
        if x < 0 or y < 0 or x + w > 1920 or y + h > 1080:
            warnings.append(f"Элемент {i} выходит за пределы слайда (0-1920x1080)")
        bounds_list.append((i, b))

    # Проверка пересечений
    for i in range(len(bounds_list)):
        for j in range(i+1, len(bounds_list)):
            idx1, b1 = bounds_list[i]
            idx2, b2 = bounds_list[j]
            if check_intersection(b1, b2):
                # Исключаем явно вложенные элементы? Пока считаем любое пересечение ошибкой
                warnings.append(f"Пересечение элементов {idx1} и {idx2}")
    return warnings