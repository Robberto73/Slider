# agents/page_generator.py
import yaml
import json
import re
from pathlib import Path
from typing import Dict, Any, Optional, List
from agents.base import BaseLLM
from tools.icon_tool import IconTool
from tools.chart_tool import ChartTool
from tools.layout_tool import LayoutTool, SlideRole, Placeholder
from tools.yaml_validator import YamlValidator

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
        user = f"Страница: {page_name}. {extra}"
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ]

        # Максимум 3 попытки генерации с самооценкой
        best_page = None
        best_score = 0
        for attempt in range(3):
            if attempt > 0:
                # Передаём замечания и просим исправить
                critique = self._get_critique(best_page, role)
                messages.append({"role": "user", "content": f"Предыдущая версия имеет недостатки: {critique}. Исправь YAML."})

            response = self.llm.chat(messages, temperature=0.4, max_tokens=2000)
            messages.append({"role": "assistant", "content": response})

            yaml_str = self._extract_yaml(response)
            try:
                page = yaml.safe_load(yaml_str)
                if not isinstance(page, dict):
                    continue
            except Exception:
                continue

            self._process_placeholders(page)
            self._enforce_grid(page, placeholders)
            page = YamlValidator.validate_and_fix(page, placeholders, self.theme)

            # Оценка качества
            score = self._evaluate_page(page, role)
            if score >= 8:  # отлично, сразу возвращаем
                return page
            if score > best_score:
                best_score = score
                best_page = page
            # иначе продолжаем цикл с замечаниями

        return best_page if best_page else self._fallback_page(role)

    def _evaluate_page(self, page: Dict, role: SlideRole) -> int:
        """Быстрый оценочный промпт: возвращает число от 1 до 10."""
        yaml_dump = yaml.dump(page, allow_unicode=True)
        prompt = (
            f"Оцени качество слайда по шкале 1-10. Слайд роли {role.value}. "
            f"Содержимое YAML:\n{yaml_dump}\n\n"
            "Критерии:\n"
            "- Заполненность контентом (нет пустых блоков)\n"
            "- Иконки адекватного размера (не гигантские)\n"
            "- Текст читаем и не выходит за границы\n"
            "- Соответствует своей роли\n"
            "Укажи только число (1-10)."
        )
        try:
            resp = self.llm.chat([{"role": "user", "content": prompt}], temperature=0, max_tokens=10)
            # Извлекаем число
            match = re.search(r'\b(10|[1-9])\b', resp)
            if match:
                return int(match.group(1))
        except Exception:
            pass
        return 5  # средняя оценка при ошибке

    def _get_critique(self, page: Dict, role: SlideRole) -> str:
        """Возвращает краткие замечания по слайду."""
        yaml_dump = yaml.dump(page, allow_unicode=True)
        prompt = (
            f"Слайд роли {role.value} имеет следующие недостатки. YAML:\n{yaml_dump}\n\n"
            "Напиши кратко (2-3 предложения), что нужно исправить, чтобы улучшить слайд."
        )
        try:
            resp = self.llm.chat([{"role": "user", "content": prompt}], temperature=0.3, max_tokens=150)
            return resp.strip()
        except Exception:
            return "Улучши читаемость и компоновку."

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
        placeholder_desc = LayoutTool.describe_placeholders(placeholders)

        prompt = f"""Ты — профессиональный дизайнер слайдов. Размести контент в заданной сетке.

СЕТКА СЛАЙДА (роль: {role.value}):
{placeholder_desc}

ДОСТУПНЫЕ ЦВЕТА:
{color_desc}

ПРАВИЛА:
1. Заголовок — ОДНА строка, стиль $title (fontSize 36).
2. Основной текст — стиль $body (fontSize 20). Каждый параграф ≤ 4 строк.
3. Иконки-маркеры для списков СТРОГО 40x40 px. Декоративные иконки ≤ 200x200 px.
4. Не меняй bounds плейсхолдеров, не выходи за границы.
5. Между элементами отступ минимум 20 px.
6. Не обрамляй iconName в кавычки внутри YAML.

ПРИМЕР ИДЕАЛЬНОГО СЛАЙДА (content_with_icons):
```yaml
background:
  type: solid
  color: "$bgLight"
elements:
  - elementType: text
    bounds: [120, 80, 1680, 120]
    content:
      text: "Предпосылки и проблематика"
      style: "$title"
      align: [left, middle]
  - elementType: text
    bounds: [120, 300, 800, 550]
    content:
      text: "<b>Географические аномалии</b>\\n\\nПользователи из разных регионов...\\n\\n<b>Несоответствие ИНН и IP</b>\\n\\nРегион регистрации не совпадает..."
      style: "$body"
      align: [left, top]
  - elementType: icon
    bounds: [120, 300, 40, 40]
    iconName: <<ICON:map-pin|regular>>
  - elementType: icon
    bounds: [120, 450, 40, 40]
    iconName: <<ICON:identification-badge|regular>>
```
Создай слайд.
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
                        if "colors" not in element:
                            element["colors"] = ["$accent", "$primary", "$textLight"]
                    else:
                        element["type"] = chart_type
                        element["data"] = [{"категория": f"Пример {i}", "значение": 10 * (i + 1)} for i in range(count)]

    def _enforce_grid(self, page: Dict, placeholders):
        allowed = []

        for el in page.get("elements", []):
            if "bounds" not in el:
                continue
            x, y, w, h = el["bounds"]
            for ph in placeholders:
                px, py, pw, ph_h = ph.bounds
                if x >= px and y >= py and x + w <= px + pw and y + h <= py + ph_h:
                    allowed.append(el)
                    break
        page["elements"] = allowed

    def _normalize_icon_sizes(self, page: Dict):
        for el in page.get("elements", []):
            if el.get("elementType") == "icon" and "bounds" in el:
                if el["bounds"][2] > 200 or el["bounds"][3] > 200:
                    el["bounds"][2] = min(el["bounds"][2], 200)
                    el["bounds"][3] = min(el["bounds"][3], 200)

    def _fix_font_styles(self, page: Dict):
        for el in page.get("elements", []):
            if el.get("elementType") == "text":
                style = el.get("content", {}).get("style", "")
                if style not in ["$title", "$subtitle", "$body", "$small"]:
                    el["content"]["style"] = "$body"

    def _auto_fit_text(self, page: Dict):
        for el in page.get("elements", []):
            if el.get("elementType") == "text":
                text = el.get("content", {}).get("text", "")
                bounds = el.get("bounds", [0, 0, 800, 600])
                style = el.get("content", {}).get("style", "$body")

                # Если текст длиннее 100 символов для title, уменьшить шрифт
                if style == "$title" and len(text) > 100:
                    el["content"]["style"] = "$subtitle"

    def _fallback_page(self, role: SlideRole) -> Dict:
        return {
            "background": {"type": "solid", "color": "$primary"},
            "elements": [
                {"elementType": "text", "bounds": [200, 300, 1520, 200],
                 "content": {"text": "Слайд не сгенерирован", "style": "$title", "align": ["center", "middle"]}}
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