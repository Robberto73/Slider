# agents/page_generator.py
import yaml
import re
from pathlib import Path
from typing import Dict, Any, Optional
from agents.base import BaseLLM
from tools.icon_tool import IconTool
from tools.chart_tool import ChartTool
from tools.layout_tool import LayoutTool, SlideRole, Placeholder

class PageGenerator:
    def __init__(self, llm: BaseLLM, theme: Dict, icon_tool: Optional[IconTool] = None,
                 chart_tool: Optional[ChartTool] = None, improver_tool=None):
        self.llm = llm
        self.theme = theme
        self.icon_tool = icon_tool
        self.chart_tool = chart_tool
        self.improver_tool = improver_tool
        self.current_topic = ""

    def generate(self, page_name: str, topic: str, style: str, language: str,
                 include_charts: bool, include_icons: bool, extra: str = "",
                 role: Optional[SlideRole] = None) -> Dict[str, Any]:
        self.current_topic = topic
        if role is None:
            role = LayoutTool.classify_role(page_name)

        placeholders = LayoutTool.get_placeholders(role)
        system = self._build_system_prompt(include_charts, include_icons, role, placeholders)
        user = f"Страница: {page_name}. {extra} Тема: {topic}, стиль: {style}, язык: {language}."
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ]

        # Модель отвечает один раз, так как координаты фиксированы
        response = self.llm.chat(messages, temperature=0.5, max_tokens=2000)
        yaml_str = self._extract_yaml(response)

        try:
            page = yaml.safe_load(yaml_str)
            if not isinstance(page, dict):
                raise ValueError("Не словарь")
        except Exception:
            # fallback – пустая страница с плейсхолдерами
            page = {
                "background": {"type": "solid", "color": "$primary"},
                "elements": [
                    {
                        "elementType": "text",
                        "bounds": [200, 300, 1520, 200],
                        "content": {
                            "text": "⚠️ Ошибка генерации слайда",
                            "style": "$title",
                            "align": ["center", "middle"]
                        }
                    }
                ]
            }

        # Постобработка плейсхолдеров
        self._process_placeholders(page)
        # Фильтрация: оставляем только элементы, разрешённые сеткой
        self._enforce_grid(page, placeholders)

        return page

    def _extract_yaml(self, text: str) -> str:
        match = re.search(r'```yaml\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            return match.group(1).strip()
        match = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()

    def _build_system_prompt(self, include_charts, include_icons, role: SlideRole, placeholders):
        colors = self.theme.get("colors", {})
        color_desc = "\n".join([f"    {k}: \"{v}\"" for k, v in colors.items()])
        text_styles = self.theme.get("textStyles", {})
        styles_desc = "\n".join([
            f"    {k}: {{ fontSize: {v.get('fontSize', 18)}, fontFamily: {v.get('fontFamily', 'Inter')}, color: \"{v.get('color', '$textDark')}\" }}"
            for k, v in text_styles.items()
        ])

        placeholder_desc = LayoutTool.describe_placeholders(placeholders)

        prompt = f"""Ты — генератор контента слайда. Слайд имеет роль **{role.value}**. Используй СТРОГО следующую сетку:

{placeholder_desc}

Тема оформления:
{color_desc}
Текстовые стили:
{styles_desc}

Правила:
1. Верни **только YAML** (без ```).
2. В YAML должны быть только элементы, перечисленные в сетке.
3. Для **text** укажи style согласно fontStyle плейсхолдера (например, "$title", "$subtitle", "$body", "$small").
4. Для **icon** используй <<ICON:ключевое_слово|стиль>> (например, <<ICON:рост|bold>>).
5. Для **chart** используй <<CHART:тип|количество>> (например, <<CHART:bar|4>>).
6. Не меняй bounds ни у одного элемента.
7. Используй цвета ТОЛЬКО через переменные со знаком $ (например, $primary).

Пример заполненного слайда (роль content_with_chart):

background:
  type: solid
  color: "$primary"
elements:
  - elementType: text
    bounds: [120, 80, 1680, 120]
    content:
      text: "<b>Обзор рынка</b>"
      style: "$title"
      align: [center, middle]
  - elementType: chart
    bounds: [120, 240, 1200, 700]
    type: bar
    data: <<CHART:bar|4>>
    colors: ["$accent", "$primary"]
  - elementType: icon
    bounds: [1480, 800, 200, 200]
    iconName: "<<ICON:аналитика|regular>>"

Теперь создай слайд.
"""
        if not include_charts:
            prompt += "\nГрафики отключены. Не используй chart и <<CHART>>."
        if not include_icons:
            prompt += "\nИконки отключены. Не используй icon и <<ICON>>."
        return prompt

    def _process_placeholders(self, page: Dict):
        for element in page.get("elements", []):
            etype = element.get("elementType")
            if etype == "icon" and "iconName" in element:
                name = element["iconName"]
                if isinstance(name, str) and name.startswith("<<ICON:") and name.endswith(">>"):
                    inner = name[7:-2]
                    parts = inner.split('|')
                    query = parts[0].strip()
                    preferred_style = parts[1].strip() if len(parts) > 1 else 'regular'
                    if self.icon_tool:
                        matched = self.icon_tool.get_best_match(query, preferred_style)
                        element["iconName"] = matched if matched else "circle"
                    else:
                        element["iconName"] = "circle"
            elif etype == "chart" and "data" in element:
                data = element["data"]
                if isinstance(data, str) and data.startswith("<<CHART:") and data.endswith(">>"):
                    spec = data[8:-2]
                    parts = spec.split("|")
                    chart_type = parts[0] if parts else "bar"
                    count = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 4
                    if self.chart_tool:
                        chart_data = self.chart_tool.generate(chart_type, self.current_topic, count)
                        element["type"] = chart_type
                        element["data"] = chart_data
                        if "colors" not in element:
                            element["colors"] = ["$accent", "$primary", "$textLight"]
                    else:
                        element["type"] = chart_type
                        element["data"] = [{"категория": f"Пример {i}", "значение": 10*(i+1)} for i in range(count)]

    def _enforce_grid(self, page: Dict, placeholders):
        """Удаляет элементы, которых нет в сетке, и корректирует bounds разрешённых."""
        allowed_bounds = [p.bounds for p in placeholders]
        filtered = []
        for el in page.get("elements", []):
            if "bounds" in el and el["bounds"] in allowed_bounds:
                filtered.append(el)
            else:
                # Если координаты не совпадают точно – принудительно ставим ближайший подходящий плейсхолдер по типу
                assigned = False
                for p in placeholders:
                    if p.element_type.value == el.get("elementType"):
                        el["bounds"] = p.bounds  # жёстко перезаписываем
                        filtered.append(el)
                        assigned = True
                        break
                if not assigned:
                    # Элемент не разрешён – пропускаем
                    pass
        page["elements"] = filtered

    def improve(self, page_name: str, current_yaml: str, instruction: str,
                role: Optional[SlideRole] = None) -> Dict[str, Any]:
        """
        Улучшение существующей страницы. Вызывает генерацию заново с дополнительными инструкциями.
        """
        if role is None:
            role = LayoutTool.classify_role(page_name)
        # Передаём текущий YAML как часть контекста
        extra = f"Улучши существующий слайд: {instruction}. Текущий YAML: {current_yaml}"
        return self.generate(page_name, self.current_topic, "dark", "ru",
                             include_charts=True, include_icons=True,
                             extra=extra, role=role)