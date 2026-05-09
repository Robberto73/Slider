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

        # Один вызов модели, так как координаты основываются на плейсхолдерах
        response = self.llm.chat(messages, temperature=0.5, max_tokens=2000)
        yaml_str = self._extract_yaml(response)

        try:
            page = yaml.safe_load(yaml_str)
            if not isinstance(page, dict):
                raise ValueError("Не словарь")
        except Exception:
            page = self._fallback_page(role)

        # Постобработка: иконки/графики
        self._process_placeholders(page)
        # Удаляем элементы, выходящие за пределы разрешённых плейсхолдеров
        self._enforce_grid(page, placeholders)
        # Автоматическая корректировка: если иконка > 200px, уменьшаем
        self._normalize_icon_sizes(page)

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

        prompt = f"""Ты — дизайнер слайда. Слайд имеет роль **{role.value}**.
Вот разрешённые плейсхолдеры (координаты жёстко заданы):
{placeholder_desc}

Ты можешь размещать в этих плейсхолдерах любые элементы (text, shape, icon, chart), **но не выходить за их границы**. Допускается создавать составные блоки внутри плейсхолдеров (например, прямоугольник с заливкой + текст поверх).

Обязательные правила по оформлению:
1. Иконки должны быть **маленькими** (не более 200×200 пикселей). Используй их как маркеры списков или акценты рядом с текстом. Пример: bounds: [120, 250, 80, 80].
2. Для выделения важных блоков используй **shape** (rect, roundedRect) с цветной заливкой из темы, а поверх него размещай text.
3. Все тексты должны использовать стили из темы: $title, $subtitle, $body, $small.
4. Не размещай элементы вплотную друг к другу — оставляй отступы минимум 20px между ними.
5. Избегай слишком крупных блоков текста, разбивай на абзацы.
6. Если есть свободное место, добавь небольшой декоративный элемент (иконку или небольшой shape), но не загромождай слайд.

Пример хорошего слайда (роль title_and_content):
```yaml
background:
  type: solid
  color: "$bgLight"
elements:
  - elementType: text
    bounds: [120, 80, 1680, 120]
    content:
      text: "<b>Основные выводы</b>"
      style: "$title"
      align: [center, middle]
  - elementType: shape
    bounds: [120, 240, 1680, 600]
    shapeName: roundedRect
    fill:
      type: solid
      color: "$primary"
  - elementType: text
    bounds: [160, 280, 800, 180]
    content:
      text: "<i>Рынок вырос на 30%</i>\nОблачные сервисы и IoT стали драйверами роста."
      style: "$body"
      align: [left, top]
  - elementType: icon
    bounds: [1000, 280, 80, 80]
    iconName: "<<ICON:рост|bold>>"
  - elementType: text
    bounds: [160, 480, 800, 180]
    content:
      text: "Основные угрозы: фишинг, программы-вымогатели, DDoS."
      style: "$body"
      align: [left, top]
  - elementType: icon
    bounds: [1000, 480, 80, 80]
    iconName: "<<ICON:опасность|regular>>"
```
Теперь создай слайд для страницы, запрошенной пользователем.
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
                if isinstance(element["iconName"], dict):
                    # Пытаемся вытащить имя из словаря
                    d = element["iconName"]
                    element["iconName"] = d.get("name", d.get("iconName", "circle"))
                elif not isinstance(element["iconName"], str):
                    element["iconName"] = str(element["iconName"])
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
                    else:
                        element["type"] = chart_type
                        element["data"] = [{"категория": f"Пример {i}", "значение": 10 * (i + 1)} for i in range(count)]
                    if "colors" not in element:
                        element["colors"] = ["$accent", "$primary", "$textLight"]

    def _enforce_grid(self, page: Dict, placeholders):
        allowed = []
        for el in page.get("elements", []):
            if "bounds" not in el:
                continue
            x, y, w, h = el["bounds"]
            contained = False
            for ph in placeholders:
                px, py, pw, ph = ph.bounds
                if x >= px and y >= py and x + w <= px + pw and y + h <= py + ph:
                    contained = True
                    break
            if contained:
                allowed.append(el)
        page["elements"] = allowed  # <-- теперь после цикла

    def _normalize_icon_sizes(self, page: Dict):
        for el in page.get("elements", []):
            if el.get("elementType") == "icon" and "bounds" in el:
                w, h = el["bounds"][2], el["bounds"][3]
                if w > 200 or h > 200:
                    el["bounds"][2] = min(w, 200)
                    el["bounds"][3] = min(h, 200)

    def _fallback_page(self, role: SlideRole) -> Dict:
        return {
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

    def improve(self, page_name: str, current_yaml: str, instruction: str,
                role: Optional[SlideRole] = None) -> Dict[str, Any]:
        if role is None:
            role = LayoutTool.classify_role(page_name)
        extra = f"Улучши существующий слайд: {instruction}. Текущий YAML: {current_yaml}"
        return self.generate(page_name, self.current_topic, "dark", "ru",
                             include_charts=True, include_icons=True,
                             extra=extra, role=role)