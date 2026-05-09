"""
Пошаговый валидатор YAML слайдов.
Исправляет типовые ошибки модели, нормализует размеры, шрифты, данные.
"""

from typing import Dict, List, Optional, Any
from tools.layout_tool import LayoutTool, SlideRole, Placeholder


class YamlValidator:
    @staticmethod
    def validate_and_fix(page: Dict, placeholders: List[Placeholder], theme: Dict) -> Dict:
        """
        Принимает YAML-страницу (словарь), список плейсхолдеров и тему.
        Возвращает исправленную страницу.
        """
        # Исправляем фон
        if not page.get("background"):
            page["background"] = {"type": "solid", "color": "$primary"}
        bg_color = page["background"].get("color", "$primary")
        if not bg_color.startswith("$"):
            page["background"]["color"] = "$primary"

        elements = page.get("elements", [])
        text_styles = theme.get("textStyles", {})

        for el in elements:
            el_type = el.get("elementType")

            # Универсальные исправления
            if "bounds" not in el or len(el.get("bounds", [])) != 4:
                continue  # такой элемент будет удалён позже enforce_grid

            # --- TEXT ---
            if el_type == "text":
                content = el.setdefault("content", {})
                # Убедимся, что style корректен
                style = content.get("style", "$body")
                if style not in text_styles and not style.startswith("$"):
                    content["style"] = "$body"
                # Добавим align если нет
                if "align" not in content:
                    content["align"] = ["left", "top"]
                # Автофит текста: обрежем очень длинный текст под размер бокса
                bounds = el["bounds"]
                max_chars = YamlValidator._estimate_max_chars(bounds, content.get("style", "$body"), text_styles)
                text = content.get("text", "")
                if len(text) > max_chars:
                    content["text"] = text[:max_chars] + "…"

            # --- ICON ---
            elif el_type == "icon":
                # Убедимся, что iconName – строка
                if not isinstance(el.get("iconName"), str):
                    el["iconName"] = "circle"
                # Нормализуем размер иконок
                bounds = el.get("bounds", [0, 0, 80, 80])
                if bounds[2] > 200: bounds[2] = 200
                if bounds[3] > 200: bounds[3] = 200
                if bounds[2] < 20: bounds[2] = 40
                if bounds[3] < 20: bounds[3] = 40

            # --- CHART ---
            elif el_type == "chart":
                if "type" not in el:
                    el["type"] = "bar"
                if "data" not in el or not isinstance(el["data"], list):
                    el["data"] = [{"категория": "Нет данных", "значение": 1}]
                if "colors" not in el:
                    el["colors"] = ["$accent", "$primary"]
                # Убедимся, что bounds разумного размера
                bounds = el.get("bounds", [0, 0, 400, 300])
                if bounds[2] < 100: bounds[2] = 400
                if bounds[3] < 100: bounds[3] = 300

            # --- SHAPE ---
            elif el_type == "shape":
                if "fill" not in el:
                    el["fill"] = {"type": "solid", "color": "$accent"}
                if "shapeName" not in el:
                    el["shapeName"] = "rect"

        # Удаляем элементы с явно невалидными bounds (защита)
        page["elements"] = [
            el for el in elements
            if len(el.get("bounds", [])) == 4
        ]

        return page

    @staticmethod
    def _estimate_max_chars(bounds: List[int], style: str, text_styles: Dict) -> int:
        """Приблизительно оценивает, сколько символов поместится в блоке."""
        width, height = bounds[2], bounds[3]
        style_info = text_styles.get(style.lstrip("$"), {})
        font_size = style_info.get("fontSize", 18)
        # Грубая оценка: средняя ширина символа ~0.5 * font_size px, межстрочный интервал ~1.5 * font_size
        char_width = font_size * 0.5
        lines = height // (font_size * 1.5)
        if lines < 1: lines = 1
        chars_per_line = width // char_width
        return int(chars_per_line * lines * 0.8)  # запас 20%