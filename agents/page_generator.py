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

    # ═══════════════════════════════════════════════════════════
    # ПУБЛИЧНЫЕ МЕТОДЫ
    # ═══════════════════════════════════════════════════════════

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

        best_page = None
        best_score = -1

        for attempt in range(3):
            if attempt > 0:
                critique = self._get_critique(best_page, role)
                messages.append({
                    "role": "user",
                    "content": f"Предыдущая версия имеет недостатки: {critique}. Исправь YAML."
                })

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
            self._enforce_grid_soft(page, placeholders)
            self._normalize_icon_sizes(page)
            self._fix_font_styles(page)
            self._auto_fit_text(page)
            page = YamlValidator.validate_and_fix(page, placeholders, self.theme)

            score = self._evaluate_page_fast(page, role)
            if score >= 8:
                return page
            if score > best_score:
                best_score = score
                best_page = page

        return best_page if best_page else self._fallback_page(role)

    def improve(self, page_name: str, current_yaml: str, instruction: str,
                role: Optional[SlideRole] = None) -> Dict[str, Any]:
        if role is None:
            role = LayoutTool.classify_role(page_name)

        extra = f"Улучши существующий слайд: {instruction}. Текущий YAML: {current_yaml}"
        return self.generate(page_name, self.current_topic, "dark", "ru",
                             include_charts=True, include_icons=True,
                             extra=extra, role=role)

    # ═══════════════════════════════════════════════════════════
    # ДЕТЕРМИНИРОВАННАЯ ОЦЕНКА КАЧЕСТВА (замена LLM-оценки)
    # ═══════════════════════════════════════════════════════════

    def _evaluate_page_fast(self, page: Dict, role: SlideRole) -> int:
        """Детерминированная оценка 0-10. Не требует вызова LLM."""
        score = 10
        elements = page.get("elements", [])
        bg = page.get("background", {})

        # --- Критические ошибки ---
        if not elements:
            return 1

        texts = [e for e in elements if e.get("elementType") == "text"]
        if not texts:
            score -= 4

        empty_texts = 0
        for t in texts:
            txt = t.get("content", {}).get("text", "")
            if not txt or txt.strip() in ("TODO", "Слайд не сгенерирован", "Слайд в процессе генерации", ""):
                empty_texts += 1
        if empty_texts == len(texts) and texts:
            score -= 3

        # Фон: для светлых тем чёрный фон — ошибка
        bg_color = bg.get("color", "") if isinstance(bg, dict) else ""
        colors = self.theme.get("colors", {})
        if bg_color == "$primary" and role != SlideRole.COVER:
            if colors.get("bgLight"):
                score -= 2

        # --- Структурные проверки ---
        has_title = any(
            t.get("content", {}).get("style", "") == "$title"
            for t in texts
        )
        if not has_title and role not in (SlideRole.BLANK,):
            score -= 2

        out_of_bounds = 0
        for e in elements:
            b = e.get("bounds", [0, 0, 0, 0])
            if len(b) == 4:
                if b[0] < 0 or b[1] < 0 or b[0] + b[2] > 1920 or b[1] + b[3] > 1080:
                    out_of_bounds += 1
        if out_of_bounds > 0:
            score -= min(2, out_of_bounds)

        if len(elements) < 2:
            score -= 2
        if len(elements) > 15:
            score -= 1

        icons = [e for e in elements if e.get("elementType") == "icon"]
        oversized_icons = sum(1 for i in icons if i.get("bounds", [0, 0, 0, 0])[2] > 300)
        if oversized_icons > 0:
            score -= 1

        overlaps = self._count_overlaps(elements)
        if overlaps > 3:
            score -= 2
        elif overlaps > 0:
            score -= 1

        return max(0, min(10, score))

    def _count_overlaps(self, elements: List[Dict]) -> int:
        """Считает пары пересекающихся элементов."""
        count = 0
        for i, e1 in enumerate(elements):
            b1 = e1.get("bounds", [])
            if len(b1) != 4:
                continue
            for e2 in elements[i + 1:]:
                b2 = e2.get("bounds", [])
                if len(b2) != 4:
                    continue
                if (b1[0] < b2[0] + b2[2] and b1[0] + b1[2] > b2[0] and
                        b1[1] < b2[1] + b2[3] and b1[1] + b1[3] > b2[1]):
                    count += 1
        return count

    # ═══════════════════════════════════════════════════════════
    # МЯГКАЯ ПРИВЯЗКА К СЕТКЕ (замена жёсткого enforce_grid)
    # ═══════════════════════════════════════════════════════════

    def _enforce_grid_soft(self, page: Dict, placeholders: List[Placeholder]):
        """Корректирует bounds вместо удаления элементов."""
        corrected = []
        for el in page.get("elements", []):
            if "bounds" not in el or len(el.get("bounds", [])) != 4:
                continue
            x, y, w, h = el["bounds"]

            # Находим ближайший плейсхолдер по пересечению
            best_ph = None
            best_overlap = 0
            for ph in placeholders:
                px, py, pw, ph_h = ph.bounds
                overlap_x = max(0, min(x + w, px + pw) - max(x, px))
                overlap_y = max(0, min(y + h, py + ph_h) - max(y, py))
                overlap = overlap_x * overlap_y
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_ph = ph

            if best_ph and best_overlap > 0:
                px, py, pw, ph_h = best_ph.bounds
                new_x = max(x, px)
                new_y = max(y, py)
                new_w = min(w, px + pw - new_x)
                new_h = min(h, py + ph_h - new_y)
                if new_w >= 20 and new_h >= 20:
                    el["bounds"] = [new_x, new_y, new_w, new_h]
                    corrected.append(el)
            else:
                # Нет пересечения — проверяем границы слайда
                if 0 <= x < 1920 and 0 <= y < 1080 and w > 0 and h > 0:
                    new_w = min(w, 1920 - x)
                    new_h = min(h, 1080 - y)
                    if new_w >= 20 and new_h >= 20:
                        el["bounds"] = [x, y, new_w, new_h]
                        corrected.append(el)

        page["elements"] = corrected

    # ═══════════════════════════════════════════════════════════
    # ОСТАЛЬНЫЕ МЕТОДЫ (с минимальными изменениями)
    # ═══════════════════════════════════════════════════════════

    def _get_critique(self, page: Dict, role: SlideRole) -> str:
        """Возвращает краткие замечания по слайду."""
        if not page:
            return "Слайд пуст или некорректен. Создай полноценный слайд с заголовком и контентом."
        yaml_dump = yaml.dump(page, allow_unicode=True)
        prompt = (
            f"Слайд роли {role.value} имеет следующие недостатки. YAML:\n{yaml_dump}\n\n"
            "Напиши кратко (2-3 предложения), что нужно исправить, чтобы улучшить слайд."
        )
        try:
            resp = self.llm.chat([{"role": "user", "content": prompt}],
                                 temperature=0.3, max_tokens=150)
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

    def _process_placeholders(self, page: Dict):
        for element in page.get("elements", []):
            etype = element.get("elementType")

            if etype == "icon" and "iconName" in element:
                name = element["iconName"]
                if isinstance(name, str) and name.startswith("<>"):
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
                if isinstance(data, str) and data.startswith("<>"):
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
                style = el.get("content", {}).get("style", "$body")
                if style == "$title" and len(text) > 100:
                    el["content"]["style"] = "$subtitle"

    def _fallback_page(self, role: SlideRole) -> Dict:
        """Гарантированно валидный fallback с правильными цветами."""
        colors = self.theme.get("colors", {})
        bg = colors.get("bgLight", "#F0EDEA")
        text = colors.get("textDark", "#1C2524")

        return {
            "background": {"type": "solid", "color": bg},
            "elements": [
                {
                    "elementType": "text",
                    "bounds": [200, 300, 1520, 200],
                    "content": {
                        "text": "Слайд в процессе генерации",
                        "style": "$title",
                        "align": ["center", "middle"],
                        "color": text
                    }
                }
            ]
        }

    def _build_system_prompt(self, include_charts, include_icons, role: SlideRole, placeholders):
        colors = self.theme.get("colors", {})
        color_desc = "\n".join([f" {k}: \"{v}\"" for k, v in colors.items()])
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
      text: " **Географические аномалии**\\n\\nПользователи из разных регионов...\\n\\n **Несоответствие ИНН и IP**\\n\\nРегион регистрации не совпадает..."
      style: "$body"
      align: [left, top]
  - elementType: icon
    bounds: [120, 300, 40, 40]
    iconName: <>
  - elementType: icon
    bounds: [120, 450, 40, 40]
    iconName: <>
```
Создай слайд.
"""
#ПРИМЕР ИДЕАЛЬНОГО СЛАЙДА (content_with_icons):
#```yaml
#background:
#  type: solid
#  color: "$bgLight"
#elements:
#  - elementType: text
#    bounds: [120, 80, 1680, 120]
#    content:
#      text: "Предпосылки и проблематика"
#      style: "$title"
#      align: [left, middle]
#  - elementType: text
#    bounds: [120, 300, 800, 550]
#    content:
#      text: "<b>Географические аномалии</b>\\n\\nПользователи из разных регионов...\\n\\n<b>Несоответствие ИНН и IP</b>\\n\\nРегион регистрации не совпадает..."
#      style: "$body"
#      align: [left, top]
#  - elementType: icon
#    bounds: [120, 300, 40, 40]
#    iconName: <<ICON:map-pin|regular>>
#  - elementType: icon
#    bounds: [120, 450, 40, 40]
#    iconName: <<ICON:identification-badge|regular>>
#```
#Создай слайд.
#"""
        if not include_charts:
            prompt += "\nГрафики отключены. Не используй chart и <<CHART>>."
        if not include_icons:
            prompt += "\nИконки отключены. Не используй icon и <<ICON>>."
        return prompt
