# tools/slide_validator.py
from typing import Dict, List, Tuple, Any


class SlideValidator:
    """Минимальный валидатор слайдов для авто-перегенерации"""

    SLIDE_WIDTH = 1920
    SLIDE_HEIGHT = 1080
    MIN_ELEMENTS = 2
    MAX_TEXT_LENGTH = {"$title": 80, "$subtitle": 120, "$body": 300}

    @classmethod
    def validate(cls, page: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Проверяет слайд на критические ошибки.
        Возвращает: (is_valid: bool, errors: List[str])
        """
        errors = []
        elements = page.get("elements", [])

        # 1️⃣ Проверка: минимум элементов
        if len(elements) < cls.MIN_ELEMENTS:
            errors.append(f"Мало элементов: {len(elements)} < {cls.MIN_ELEMENTS}")

        # 2️⃣ Проверка: пересечения элементов
        overlaps = cls._check_overlaps(elements)
        if overlaps:
            errors.append(f"Пересечения: {overlaps}")

        # 3️⃣ Проверка: валидность цветов
        color_errors = cls._check_colors(page)
        if color_errors:
            errors.extend(color_errors)

        # 4️⃣ Проверка: длина текста
        text_errors = cls._check_text_lengths(elements)
        if text_errors:
            errors.extend(text_errors)

        # 5️⃣ Проверка: границы слайда
        bounds_errors = cls._check_bounds(elements)
        if bounds_errors:
            errors.extend(bounds_errors)

        return len(errors) == 0, errors

    @staticmethod
    def _check_overlaps(elements: List[Dict]) -> List[str]:
        """Проверяет пересечения bounding box элементов"""
        overlaps = []
        for i, el1 in enumerate(elements):
            if "bounds" not in el1:
                continue
            x1, y1, w1, h1 = el1["bounds"]
            for j, el2 in enumerate(elements[i + 1:], start=i + 1):
                if "bounds" not in el2:
                    continue
                x2, y2, w2, h2 = el2["bounds"]
                # Простая проверка пересечения прямоугольников
                if (x1 < x2 + w2 and x1 + w1 > x2 and
                        y1 < y2 + h2 and y1 + h1 > y2):
                    overlaps.append(f"{el1.get('elementType')}#{i} ↔ {el2.get('elementType')}#{j}")
        return overlaps

    @staticmethod
    def _check_colors(page: Dict) -> List[str]:
        """Проверяет, что цвета используют переменные темы ($...)"""
        errors = []
        valid_prefixes = ("$",)  # можно расширить: "$", "var(--"

        def scan(obj, path=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in ("color", "fill", "stroke") and isinstance(v, str):
                        if v and not v.startswith(valid_prefixes) and not v.startswith("#"):
                            errors.append(f"Невалидный цвет в {path}.{k}: '{v}'")
                    else:
                        scan(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for idx, item in enumerate(obj):
                    scan(item, f"{path}[{idx}]")

        scan(page)
        return errors

    @staticmethod
    def _check_text_lengths(elements: List[Dict]) -> List[str]:
        """Проверяет, не превышает ли текст лимиты для своего стиля"""
        errors = []
        for el in elements:
            if el.get("elementType") != "text":
                continue
            content = el.get("content", {})
            text = content.get("text", "")
            style = content.get("style", "$body")
            # Убираем $ для поиска в словаре
            style_key = style.lstrip("$")
            max_len = SlideValidator.MAX_TEXT_LENGTH.get(style_key, 300)
            # Считаем длину без маркдауна и переносов
            clean_len = len(text.replace("**", "").replace("\n", " "))
            if clean_len > max_len * 1.5:  # +50% буфер
                errors.append(f"Текст в стиле '{style}' слишком длинный: {clean_len} > {max_len}")
        return errors

    @staticmethod
    def _check_bounds(elements: List[Dict]) -> List[str]:
        """Проверяет, что элементы не выходят за границы слайда"""
        errors = []
        for i, el in enumerate(elements):
            if "bounds" not in el:
                continue
            x, y, w, h = el["bounds"]
            if x < 0 or y < 0 or x + w > SlideValidator.SLIDE_WIDTH or y + h > SlideValidator.SLIDE_HEIGHT:
                errors.append(f"Элемент #{i} ({el.get('elementType')}) выходит за границы слайда")
        return errors

    @classmethod
    def format_errors_for_llm(cls, errors: List[str]) -> str:
        """Форматирует ошибки в понятную инструкцию для LLM"""
        if not errors:
            return ""
        return (
                "❗ КРИТИЧЕСКИЕ ОШИБКИ В СЛАЙДЕ (исправь их в новой версии):\n"
                + "\n".join(f"  • {err}" for err in errors)
                + "\n\nВерни ИСПРАВЛЕННЫЙ YAML слайда, без пояснений, без ```yaml."
        )