# agents/page_generator.py (заменяем целиком)
import yaml, json, re
from pathlib import Path
from typing import Dict, Any, Optional
from agents.base import BaseLLM
from tools.icon_tool import IconTool
from tools.chart_tool import ChartTool

class PageGenerator:
    def __init__(self, llm: BaseLLM, theme: Dict, icon_tool: Optional[IconTool] = None, chart_tool: Optional[ChartTool] = None):
        self.llm = llm
        self.theme = theme
        self.icon_tool = icon_tool
        self.chart_tool = chart_tool

    def generate(self, page_name: str, topic: str, style: str, language: str,
                 include_charts: bool, include_icons: bool, extra: str = "") -> Dict[str, Any]:
        system = self._build_system_prompt(include_charts, include_icons)
        user = f"Страница: {page_name}. {extra} Тема: {topic}, стиль: {style}, язык: {language}."
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ]
        max_iter = 5
        for iteration in range(max_iter):
            response = self.llm.chat(messages, temperature=0.4, max_tokens=1500)
            messages.append({"role": "assistant", "content": response})
            if not response.strip().startswith("NEED_"):
                yaml_str = self._extract_yaml(response)
                try:
                    page = yaml.safe_load(yaml_str)
                    if not isinstance(page, dict):
                        raise ValueError("Не словарь")
                except Exception:
                    messages.append({"role": "user", "content": "Невалидный YAML. Повтори только YAML."})
                    continue
                self._process_placeholders(page)
                return page
            if "NEED_ICON:" in response:
                descriptions = re.findall(r'NEED_ICON:\s*(.*?)(?=NEED_ICON|NEED_CHART|$)', response, re.DOTALL)
                for desc in descriptions:
                    desc = desc.strip().rstrip('.').strip()
                    # Пытаемся извлечь стиль, если есть
                    parts = desc.split('|')
                    query = parts[0].strip()
                    preferred_style = parts[1].strip() if len(parts) > 1 else 'regular'
                    if self.icon_tool:
                        icon_name = self.icon_tool.get_best_match(query, preferred_style)
                        result = f"ICON_RESULT: use iconName: \"{icon_name}\"" if icon_name else "ICON_RESULT: no match"
                    else:
                        result = "ICON_RESULT: icons not available"
                    messages.append({"role": "tool", "content": result, "name": "icon_search"})
                continue
            if "NEED_CHART:" in response:
                desc_match = re.search(r'NEED_CHART:\s*(\S+)', response)
                if desc_match:
                    spec = desc_match.group(1)
                    parts = spec.split("|")
                    chart_type = parts[0] if parts else "bar"
                    count = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 4
                    if self.chart_tool:
                        data = self.chart_tool.generate(chart_type, topic)
                        result = f"CHART_RESULT: type={chart_type}, data={json.dumps(data)}"
                    else:
                        result = "CHART_RESULT: charts not available"
                    messages.append({"role": "tool", "content": result, "name": "chart_generator"})
                continue
            messages.append({"role": "user", "content": "Пожалуйста, выдай финальный YAML слайда."})
        raise RuntimeError(f"Не удалось сгенерировать {page_name} за {max_iter} итераций")

    def _extract_yaml(self, text: str) -> str:
        match = re.search(r'```yaml\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            return match.group(1).strip()
        match = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()

    def _build_system_prompt(self, include_charts, include_icons):
        # Подставляем реальные цвета и стили из self.theme
        colors = self.theme.get("colors", {})
        color_desc = "\n".join([f"    {k}: \"{v}\"" for k, v in colors.items()])
        text_styles = self.theme.get("textStyles", {})
        styles_desc = "\n".join([
            f"    {k}: {{ fontSize: {v.get('fontSize', 18)}, fontFamily: {v.get('fontFamily', 'Inter')}, color: \"{v.get('color', '$textDark')}\" }}"
            for k, v in text_styles.items()
        ])

        prompt = f"""Ты — генератор слайда презентации в формате Kimi PPTD (YAML). Используй тему ниже.

    Тема (colors и textStyles):
    theme:
      colors:
    {color_desc}
      textStyles:
    {styles_desc}

    Создай ТОЛЬКО содержимое слайда в виде валидного YAML без обрамляющих ```. Структура:

    background:
      type: solid
      color: "$primary"   # или другой цвет из theme со знаком $

    elements:
      - elementType: text
        bounds: [x, y, width, height]   # пиксели, слайд 1920×1080
        content:
          text: "Текст (<b>жирный</b>, <i>курсив</i>)"
          style: "$title"               # имя стиля из textStyles
          align: [center, middle]       # горизонталь: left/center/right, вертикаль: top/middle/bottom

      - elementType: icon
        iconName: "имя_иконки"          # можно <<ICON:описание|стиль>> (например, <<ICON:щит|bold>>)
        bounds: [...]

      - elementType: chart
        type: bar
        data:                          # данные ИЛИ <<CHART:тип|количество_точек>>
          - {{"категория": "А", "значение": 34}}
          - {{"категория": "Б", "значение": 56}}
        colors: ["$accent", "$primary"]
        bounds: [...]

    Важно:
    - Слайд 1920×1080 пикселей. Все bounds должны быть в этих пределах.
    - Наполни слайд минимум 2-3 элементами (текст + иконка/график/фигура).
    - Иконки: используй placeholder <<ICON:ключевое_слово|стиль>>. Стили: thin, light, regular, bold, fill, duotone.
    - Графики: используй placeholder <<CHART:тип|количество>> (например, <<CHART:bar|4>>) или свои числа, но строго больше 0.
    - Цвета только со знаком $ из theme.

    Пример качественного слайда:

    background:
      type: solid
      color: "$primary"
    elements:
      - elementType: text
        bounds: [120, 200, 1680, 300]
        content:
          text: "<b>Ключевые выводы</b>"
          style: "$title"
          align: [center, middle]
      - elementType: text
        bounds: [120, 500, 1680, 400]
        content:
          text: "Рынок кибербезопасности вырос на 30% за последний год. Основные драйверы — облачные технологии и IoT."
          style: "$body"
          align: [left, top]
      - elementType: icon
        iconName: "<<ICON:безопасность|bold>>"
        bounds: [1600, 800, 200, 200]
      - elementType: chart
        type: bar
        data:
          - {{"сегмент": "Облачные", "оборот": 340}}
          - {{"сегмент": "IoT", "оборот": 280}}
          - {{"сегмент": "Мобильные", "оборот": 210}}
        colors: ["$accent", "$primary", "$textLight"]
        bounds: [200, 300, 1520, 500]

    Теперь создай слайд для страницы, которую запросил пользователь.
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
                    inner = name[7:-2]  # "описание|стиль"
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
                        chart_data = self.chart_tool.generate(chart_type, "topic", count)
                        element["type"] = chart_type
                        element["data"] = chart_data
                        if "colors" not in element:
                            element["colors"] = ["$accent", "$secondary", "$primary"]
                    else:
                        element["type"] = chart_type
                        element["data"] = [{"категория": f"Пример {i}", "значение": 10*(i+1)} for i in range(count)]