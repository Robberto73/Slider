# tools/layout_tool.py
"""
Инструмент разметки слайдов по принципу Kimi: Grid-based Layout.
Каждый тип слайда имеет жёстко заданные регионы (плейсхолдеры),
в которые модель должна помещать контент. Модель не может менять координаты.
"""

from enum import Enum
from typing import List, Dict, Optional, Tuple

class ElementType(str, Enum):
    TEXT = "text"
    CHART = "chart"
    ICON = "icon"
    TABLE = "table"
    SHAPE = "shape"

class Placeholder:
    """Описание одного плейсхолдера."""
    def __init__(self, element_type: ElementType, bounds: List[int],
                 role: str = "", max_chars: int = 500, font_style: str = "body"):
        self.element_type = element_type
        self.bounds = bounds  # [x, y, width, height]
        self.role = role      # например, "title", "content", "icon"
        self.max_chars = max_chars
        self.font_style = font_style  # title, subtitle, body, small

    def to_dict(self) -> Dict:
        return {
            "elementType": self.element_type.value,
            "bounds": self.bounds,
            "role": self.role,
            "maxChars": self.max_chars,
            "fontStyle": self.font_style
        }

class SlideRole(Enum):
    COVER = "cover"
    TITLE_AND_CONTENT = "title_and_content"
    TWO_CONTENT = "two_content"
    CONTENT_WITH_CHART = "content_with_chart"
    CONTENT_WITH_TABLE = "content_with_table"
    CONCLUSION = "conclusion"
    BLANK = "blank"

# Предопределённые шаблоны для ролей (сетка)
# Координаты подобраны для слайда 1920x1080 с отступами
TEMPLATES = {
    SlideRole.COVER: [
        Placeholder(ElementType.TEXT, [200, 300, 1520, 200], role="title", max_chars=100, font_style="title"),
        Placeholder(ElementType.TEXT, [200, 520, 1520, 120], role="subtitle", max_chars=200, font_style="subtitle"),
        Placeholder(ElementType.ICON, [1600, 780, 200, 200], role="icon", font_style=""),
    ],
    SlideRole.TITLE_AND_CONTENT: [
        Placeholder(ElementType.TEXT, [120, 80, 1680, 120], role="title", max_chars=100, font_style="title"),
        Placeholder(ElementType.TEXT, [120, 240, 1680, 600], role="content", max_chars=800, font_style="body"),
        Placeholder(ElementType.ICON, [1560, 800, 200, 200], role="icon", font_style=""),
    ],
    SlideRole.TWO_CONTENT: [
        Placeholder(ElementType.TEXT, [120, 80, 1680, 120], role="title", max_chars=100, font_style="title"),
        Placeholder(ElementType.TEXT, [120, 240, 800, 600], role="left_content", max_chars=500, font_style="body"),
        Placeholder(ElementType.TEXT, [1000, 240, 800, 600], role="right_content", max_chars=500, font_style="body"),
    ],
    SlideRole.CONTENT_WITH_CHART: [
        Placeholder(ElementType.TEXT, [120, 80, 1680, 120], role="title", max_chars=100, font_style="title"),
        Placeholder(ElementType.CHART, [120, 240, 1200, 700], role="chart"),
        Placeholder(ElementType.ICON, [1480, 800, 200, 200], role="icon", font_style=""),
    ],
    SlideRole.CONTENT_WITH_TABLE: [
        Placeholder(ElementType.TEXT, [120, 80, 1680, 120], role="title", max_chars=100, font_style="title"),
        Placeholder(ElementType.TABLE, [120, 240, 1680, 700], role="table"),
    ],
    SlideRole.CONCLUSION: [
        Placeholder(ElementType.TEXT, [200, 300, 1520, 200], role="title", max_chars=100, font_style="title"),
        Placeholder(ElementType.TEXT, [200, 520, 1520, 300], role="summary", max_chars=500, font_style="body"),
        Placeholder(ElementType.ICON, [1600, 780, 200, 200], role="icon", font_style=""),
    ],
    SlideRole.BLANK: [
        Placeholder(ElementType.TEXT, [200, 300, 1520, 400], role="content", font_style="body"),
    ],
}

class LayoutTool:
    """Фасад для получения разметки слайда по роли."""

    @staticmethod
    def classify_role(page_name: str) -> SlideRole:
        """Определяет роль слайда по имени файла."""
        name = page_name.lower().replace(".page", "")
        if "cover" in name:
            return SlideRole.COVER
        if "conclusion" in name or "summary" in name or "end" in name:
            return SlideRole.CONCLUSION
        if "chart" in name or "graph" in name or "overview" in name or "analysis" in name or "trend" in name:
            return SlideRole.CONTENT_WITH_CHART
        if "table" in name or "comparison" in name or "matrix" in name:
            return SlideRole.CONTENT_WITH_TABLE
        if "two" in name or "compare" in name or "versus" in name:
            return SlideRole.TWO_CONTENT
        # по умолчанию – обычный контентный слайд
        return SlideRole.TITLE_AND_CONTENT

    @staticmethod
    def get_placeholders(role: SlideRole) -> List[Placeholder]:
        """Возвращает плейсхолдеры для роли."""
        return TEMPLATES.get(role, TEMPLATES[SlideRole.TITLE_AND_CONTENT])

    @staticmethod
    def describe_placeholders(placeholders: List[Placeholder]) -> str:
        """Формирует текстовое описание плейсхолдеров для промпта."""
        lines = []
        for i, ph in enumerate(placeholders):
            lines.append(
                f"  {i+1}. {ph.element_type.value} ({ph.role}): bounds={ph.bounds}, "
                f"maxChars={ph.max_chars}, fontStyle={ph.font_style}"
            )
        return "\n".join(lines)

    @staticmethod
    def get_template_yaml(role: SlideRole) -> str:
        """Генерирует YAML-заготовку для роли (без текстов)."""
        placeholders = LayoutTool.get_placeholders(role)
        elements = []
        for ph in placeholders:
            el = {
                "elementType": ph.element_type.value,
                "bounds": ph.bounds,
            }
            if ph.element_type == ElementType.TEXT:
                el["content"] = {
                    "text": "TODO",
                    "style": f"${ph.font_style}",
                    "align": ["left", "top"]
                }
            elif ph.element_type == ElementType.ICON:
                el["iconName"] = "<<ICON:placeholder|regular>>"
            elif ph.element_type == ElementType.CHART:
                el["type"] = "bar"
                el["data"] = "<<CHART:bar|4>>"
                el["colors"] = ["$accent", "$primary"]
            elements.append(el)
        template = {
            "background": {"type": "solid", "color": "$primary"},
            "elements": elements
        }
        import yaml
        return yaml.dump(template, allow_unicode=True)