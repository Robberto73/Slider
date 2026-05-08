import yaml
import json
import re
from pathlib import Path
from typing import Dict, Any, Optional
from agents.base import BaseLLM
from tools.icon_tool import IconTool
from tools.chart_tool import ChartTool


class PageGenerator:
    """Генерирует YAML одной страницы с постобработкой placeholder'ов для иконок и графиков."""

    def __init__(self, llm: BaseLLM, theme: Dict, icon_tool: Optional[IconTool] = None, chart_tool: Optional[ChartTool] = None):
        self.llm = llm
        self.theme = theme
        self.icon_tool = icon_tool
        self.chart_tool = chart_tool

    def generate(self, page_name: str, topic: str, style: str, language: str,
                 include_charts: bool, include_icons: bool) -> Dict[str, Any]:
        system = self._build_system_prompt(include_charts, include_icons)
        user = f"Страница: {page_name}. Тема: {topic}, стиль: {style}, язык: {language}."
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ]
        max_iter = 5
        for iteration in range(max_iter):
            response = self.llm.chat(messages, temperature=0.4, max_tokens=1500)
            messages.append({"role": "assistant", "content": response})

            # 1. Проверяем, не финальный ли это YAML (не начинается с NEED_)
            if not response.strip().startswith("NEED_"):
                # Считаем это финальным YAML
                yaml_str = self._extract_yaml(response)
                try:
                    page = yaml.safe_load(yaml_str)
                    if not isinstance(page, dict):
                        raise ValueError("Не словарь")
                except Exception as e:
                    messages.append({"role": "user", "content": "Невалидный YAML. Повтори только YAML."})
                    continue
                self._process_placeholders(page)
                return page

            # 2. Обработка запросов NEED_ICON / NEED_CHART
            if "NEED_ICON:" in response:
                # Извлекаем все описания (могут быть склеены)
                descriptions = re.findall(r'NEED_ICON:\s*(.*?)(?=NEED_ICON|NEED_CHART|$)', response, re.DOTALL)
                for desc in descriptions:
                    desc = desc.strip().rstrip('.').strip()
                    if self.icon_tool:
                        icon_name = self.icon_tool.get_best_match(desc)
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

            # Если модель написала что-то другое, попросим завершить
            messages.append({"role": "user", "content": "Пожалуйста, выдай финальный YAML слайда."})

        raise RuntimeError(f"Не удалось сгенерировать {page_name} за {max_iter} итераций")

    def _extract_yaml(self, text: str) -> str:
        # Удаляем возможные ```yaml ... ```
        match = re.search(r'```yaml\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            return match.group(1).strip()
        # Пробуем найти ``` без указания языка
        match = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            return match.group(1).strip()
        # Иначе возвращаем текст как есть (может быть чистый YAML)
        return text.strip()

    def _build_system_prompt(self, include_charts, include_icons):
        prompt = f"""
Ты — генератор одного слайда презентации в формате Kimi PPTD (YAML). Сгенерируй ТОЛЬКО содержимое слайда в виде YAML.

Тема и стиль заданы пользователем. Используй переданные цвета и стили из theme.

Обязательная структура слайда:
background:
  type: solid
  color: "$primary"    # или "$bgLight", "$textDark" и т.д.
elements:
  - elementType: text
    bounds: [x, y, width, height]   # пиксели, 1920x1080
    content:
      text: "Текст (можно <b>жирный</b>, <i>курсив</i>)"
      style: "$title"               # или "$body"
      align: [center, middle]       # left/center/right, top/middle/bottom
  - elementType: icon
    bounds: [...]
    # используй placeholder: <<ICON:описание>>
  - elementType: chart
    bounds: [...]
    # используй placeholder: <<CHART:тип|количество_точек>>   (например, <<CHART:bar|4>>)

Для иконок не пиши iconName напрямую, а пиши placeholder <<ICON:краткое описание нужной иконки>>. Например, <<ICON:деньги>> для денег. Система сама подставит правильное имя.

Для графиков не придумывай данные, а используй placeholder <<CHART:тип|количество_точек>>. Система сгенерирует данные и вставит type, data, colors. Например, <<CHART:pie|5>>. Тип: bar, pie, line.

Цвета используй ТОЛЬКО из theme: $primary, $accent, $bgLight, $textDark, $textLight.

Верни только YAML (без обрамляющих ```). Если тебе не нужны иконки или графики, просто не включай эти элементы.
"""
        if not include_charts:
            prompt += "\nГрафики отключены. Не используй <<CHART>>."
        if not include_icons:
            prompt += "\nИконки отключены. Не используй <<ICON>>."
        return prompt

    def _process_placeholders(self, page: Dict):
        """Заменяет <<ICON:...>> и <<CHART:...>> в элементах."""
        for element in page.get("elements", []):
            etype = element.get("elementType")
            if etype == "icon" and "iconName" in element:
                name = element["iconName"]
                if isinstance(name, str) and name.startswith("<<ICON:") and name.endswith(">>"):
                    query = name[7:-2]
                    if self.icon_tool:
                        matched = self.icon_tool.get_best_match(query)
                        element["iconName"] = matched if matched else "circle"
                    else:
                        element["iconName"] = "circle"
            elif etype == "chart" and "data" in element:
                data = element["data"]
                if isinstance(data, str) and data.startswith("<<CHART:") and data.endswith(">>"):
                    spec = data[8:-2]  # e.g. "bar|4"
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