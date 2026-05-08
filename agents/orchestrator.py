import json
import yaml
import re
from pathlib import Path
from typing import Dict, Any
from agents.base import BaseLLM, PresentationAgent
from agents.page_generator import PageGenerator
from tools.icon_tool import IconTool
from tools.chart_tool import ChartTool
from tools.page_improver import PageImproverTool

class OrchestratorAgent(PresentationAgent):
    STYLES = {
        "dark": {
            "primary": "#1E3330",
            "accent": "#C9892E",
            "bgLight": "#F0EDEA",
            "textDark": "#1C2524",
            "textLight": "#E8ECEB",
        },
        "light": {
            "primary": "#FFFFFF",
            "accent": "#C9892E",
            "bgLight": "#F8F9FA",
            "textDark": "#1A1A1A",
            "textLight": "#1A1A1A",  # на белом фоне тёмный текст
        },
        "corporate": {
            "primary": "#003366",
            "accent": "#C9892E",
            "bgLight": "#F0F2F5",
            "textDark": "#1A1A1A",
            "textLight": "#FFFFFF",
        },
        "minimal": {
            "primary": "#FFFFFF",
            "accent": "#C9892E",
            "bgLight": "#FFFFFF",
            "textDark": "#1A1A1A",
            "textLight": "#1A1A1A",
        }
    }

    def __init__(self, llm: BaseLLM, icons_dir: Path = None):
        self.llm = llm
        self.icon_tool = IconTool(icons_dir) if icons_dir else None
        self.chart_tool = ChartTool()
        self.improver_tool = PageImproverTool(llm)

    def generate(self, topic, slides_count, style, language, include_charts, include_icons, output_dir):
        plan = self._create_plan(topic, slides_count, style, language, include_charts, include_icons)
        theme = plan["theme"]
        pages = plan["pages"]

        pages_content = {}
        gen = PageGenerator(self.llm, theme, self.icon_tool, self.chart_tool)
        for i, page_name in enumerate(pages):
            # Дополнительный контекст для каждой страницы
            role = page_name.replace(".page", "").replace("_", " ").capitalize()
            extra = f"Страница {i+1} из {len(pages)}. Назначение: {role}. Тема: {topic}."
            content = gen.generate(page_name, topic, style, language, include_charts, include_icons, extra)
            pages_content[page_name] = content

        self._save(theme, pages_content, output_dir)
        return {"status": "completed", "progress": 100}

    def _create_plan(self, topic, slides_count, style, language, include_charts, include_icons):
        # Берем цвета под стиль
        colors = self.STYLES.get(style, self.STYLES["dark"])
        system = "Ты — планировщик презентаций. Отвечай строго JSON без ```json."
        user = f"""Тема: "{topic}". Слайдов: {slides_count}, стиль: {style}, язык: {language}.
Графики: {'да' if include_charts else 'нет'}, Иконки: {'да' if include_icons else 'нет'}.
Используй следующие цвета для темы:
{{
  "primary": "{colors['primary']}",
  "accent": "{colors['accent']}",
  "bgLight": "{colors['bgLight']}",
  "textDark": "{colors['textDark']}",
  "textLight": "{colors['textLight']}"
}}
Создай план из ровно {slides_count} страниц. Каждая страница должна иметь осмысленное имя (на английском, оканчивается на .page).
Верни JSON строго в формате:
{{
  "theme": {{
    "colors": ... (те же, что выше),
    "textStyles": {{
      "title": {{ "fontSize": 36, "fontFamily": "Inter", "color": "$textLight" }},
      "body": {{ "fontSize": 18, "fontFamily": "Inter", "color": "$textDark" }}
    }}
  }},
  "pages": ["cover.page", "introduction.page", ...]
}}
Ответ только JSON без каких-либо дополнительных символов.
"""

        resp = self.llm.chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                             temperature=0.2, max_tokens=800)

        # Извлечение JSON
        json_str = resp.strip()
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        start = json_str.find('{')
        end = json_str.rfind('}')
        if start != -1 and end != -1:
            json_str = json_str[start:end+1]
        else:
            raise ValueError("Не удалось найти JSON в ответе планировщика")

        try:
            plan = json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"Ошибка парсинга JSON плана: {e}\nОтвет модели:\n{resp}")
            raise ValueError("План не является валидным JSON")

        # Принудительно перезаписываем цвета из нашего словаря, чтобы модель не меняла
        plan["theme"]["colors"] = colors

        # Контроль количества страниц
        planned_pages = plan.get("pages", [])
        if len(planned_pages) != slides_count:
            if len(planned_pages) < slides_count:
                planned_pages += [f"slide_{i}.page" for i in range(len(planned_pages), slides_count)]
            else:
                planned_pages = planned_pages[:slides_count]
            plan["pages"] = planned_pages

        return plan

    def _save(self, theme, pages_content, output_dir):
        pptd = {"theme": theme, "pages": list(pages_content.keys())}
        with open(output_dir / "presentation.pptd", "w", encoding="utf-8") as f:
            yaml.dump(pptd, f, allow_unicode=True)
        pages_dir = output_dir / "pages"
        pages_dir.mkdir(exist_ok=True)
        for name, content in pages_content.items():
            with open(pages_dir / name, "w", encoding="utf-8") as f:
                yaml.dump(content, f, allow_unicode=True)

    def improve_page(self, project_dir: Path, page_name: str, instruction: str):
        pages_dir = project_dir / "pages"
        page_path = pages_dir / page_name
        if not page_path.exists():
            raise FileNotFoundError(f"Страница {page_name} не найдена в проекте")
        pptd_files = list(project_dir.glob("*.pptd"))
        theme = {}
        if pptd_files:
            with open(pptd_files[0], 'r', encoding='utf-8') as f:
                pptd = yaml.safe_load(f)
                theme = pptd.get("theme", {})
        with open(page_path, 'r', encoding='utf-8') as f:
            current_yaml = f.read()
        gen = PageGenerator(self.llm, theme, self.icon_tool, self.chart_tool, self.improver_tool)
        improved = gen.improve(page_name, current_yaml, instruction)
        with open(page_path, 'w', encoding='utf-8') as f:
            yaml.dump(improved, f, allow_unicode=True)
        return improved