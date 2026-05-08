import json
import yaml
from pathlib import Path
from typing import Dict, Any
from agents.base import BaseLLM, PresentationAgent
from agents.page_generator import PageGenerator
from tools.icon_tool import IconTool
from tools.chart_tool import ChartTool
from tools.page_improver import PageImproverTool

class OrchestratorAgent(PresentationAgent):
    def __init__(self, llm: BaseLLM, icons_dir: Path = None):
        self.llm = llm
        self.icon_tool = IconTool(icons_dir) if icons_dir else None
        self.chart_tool = ChartTool()
        self.improver_tool = PageImproverTool(llm)

    def generate(self, topic, slides_count, style, language, include_charts, include_icons, output_dir):
        # Этап 0: План (JSON)
        plan = self._create_plan(topic, slides_count, style, language, include_charts, include_icons)
        theme = plan["theme"]
        pages = plan["pages"]

        # Этап 1..N: Генерация каждой страницы
        pages_content = {}
        gen = PageGenerator(self.llm, theme, self.icon_tool, self.chart_tool)
        for p in pages:
            content = gen.generate(p, topic, style, language, include_charts, include_icons)
            pages_content[p] = content

        # Сохранение проекта
        self._save(theme, pages_content, output_dir)
        return {"status": "completed", "progress": 100}

    def _create_plan(self, topic, slides_count, style, language, include_charts, include_icons):
        system = "Ты — планировщик презентаций. Отвечай строго JSON без какого-либо оформления."
        user = f"""Тема: "{topic}". Слайдов: {slides_count}, стиль: {style}, язык: {language}.
    Графики: {'да' if include_charts else 'нет'}, Иконки: {'да' if include_icons else 'нет'}.
    Верни JSON в таком формате:
    {{
      "theme": {{
        "colors": {{
          "primary": "#1E3330",
          "accent": "#C9892E",
          "bgLight": "#F0EDEA",
          "textDark": "#1C2524",
          "textLight": "#E8ECEB"
        }},
        "textStyles": {{
          "title": {{ "fontSize": 36, "fontFamily": "Inter", "color": "$textLight" }},
          "body": {{ "fontSize": 18, "fontFamily": "Inter", "color": "$textDark" }}
        }}
      }},
      "pages": ["cover.page", "problems.page", ...]  // ровно {slides_count} имён
    }}
    Имена страниц должны отражать содержание. Ответ СТРОГО только JSON, без ```json и прочего текста.
    """
        resp = self.llm.chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                             temperature=0.2, max_tokens=800)

        # Извлекаем JSON даже если модель обернула в ```json
        import re
        # Ищем содержимое между ```json и ``` или первый '{'
        match = re.search(r'```json\s*(.*?)\s*```', resp, re.DOTALL)
        if match:
            json_str = match.group(1).strip()
        else:
            # Иначе ищем первый { и последний }
            start = resp.find('{')
            end = resp.rfind('}')
            if start != -1 and end != -1:
                json_str = resp[start:end + 1]
            else:
                raise ValueError("Не удалось найти JSON в ответе планировщика")

        try:
            plan = json.loads(json_str)
        except json.JSONDecodeError as e:
            # На всякий случай записываем ответ в лог и пробуем снова
            print(f"Ошибка парсинга JSON плана: {e}\nОтвет модели:\n{resp}")
            raise ValueError("План не является валидным JSON")

        # Проконтролируем количество страниц
        planned_pages = plan.get("pages", [])
        if len(planned_pages) != slides_count:
            # Если меньше, добавляем общие названия
            if len(planned_pages) < slides_count:
                planned_pages.extend([f"slide_{i}.page" for i in range(len(planned_pages), slides_count)])
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
        """Улучшает страницу в существующем проекте и перезаписывает её."""
        pages_dir = project_dir / "pages"
        page_path = pages_dir / page_name
        if not page_path.exists():
            raise FileNotFoundError(f"Страница {page_name} не найдена в проекте")

        # Загружаем тему из .pptd
        pptd_files = list(project_dir.glob("*.pptd"))
        if pptd_files:
            with open(pptd_files[0], 'r', encoding='utf-8') as f:
                pptd = yaml.safe_load(f)
                theme = pptd.get("theme", {})
        else:
            # fallback тема
            theme = {
                "colors": {
                    "primary": "#1E3330",
                    "accent": "#C9892E",
                    "bgLight": "#F0EDEA",
                    "textDark": "#1C2524",
                    "textLight": "#E8ECEB"
                }
            }

        with open(page_path, 'r', encoding='utf-8') as f:
            current_yaml = f.read()

        gen = PageGenerator(self.llm, theme, self.icon_tool, self.chart_tool, self.improver_tool)
        improved = gen.improve(page_name, current_yaml, instruction)

        # Сохраняем улучшенную страницу
        with open(page_path, 'w', encoding='utf-8') as f:
            yaml.dump(improved, f, allow_unicode=True)

        return improved