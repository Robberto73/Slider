# agents/orchestrator.py
import json
import yaml
import re
from pathlib import Path
from typing import Dict, Any, Optional, List
from agents.base import BaseLLM, PresentationAgent
from agents.page_generator import PageGenerator
from tools.icon_tool import IconTool
from tools.chart_tool import ChartTool
from tools.page_improver import PageImproverTool
from tools.layout_tool import LayoutTool, SlideRole

class OrchestratorAgent(PresentationAgent):
    def __init__(self, llm: BaseLLM, icons_dir: Path = None):
        self.llm = llm
        self.icon_tool = IconTool(icons_dir) if icons_dir else None
        self.chart_tool = ChartTool(llm=self.llm)  # для имён категорий
        self.improver_tool = PageImproverTool(llm)

    def generate(self, topic, slides_count, style, language,
                 include_charts, include_icons, output_dir, progress_callback=None):
        if progress_callback:
            progress_callback(5, "Планирование структуры…")

        plan = self._create_plan(topic, slides_count, style, language,
                                 include_charts, include_icons)
        theme = plan["theme"]
        pages: List[str] = plan["pages"]

        gen = PageGenerator(self.llm, theme, self.icon_tool, self.chart_tool)
        pages_content: Dict[str, Any] = {}

        for i, page_name in enumerate(pages):
            pct = 5 + int((i / len(pages)) * 80)
            if progress_callback:
                progress_callback(pct, f"Генерация слайда {i+1} из {len(pages)}: {page_name}")

            # Определяем роль слайда по имени
            role: SlideRole = LayoutTool.classify_role(page_name)
            # Формируем контекст с ролью и уникальным требованием
            extra = (
                f"Страница {i+1} из {len(pages)}. "
                f"Роль слайда: {role.value}. "
                f"Тема: {topic}. "
                f"Стиль оформления: {style}. "
                f"Язык: {language}. "
                f"Создай уникальное содержимое, не повторяй заголовки других слайдов."
            )
            content = gen.generate(page_name, topic, style, language,
                                   include_charts, include_icons, extra, role)
            pages_content[page_name] = content

        if progress_callback:
            progress_callback(90, "Сохранение проекта…")
        self._save(theme, pages_content, output_dir)

        if progress_callback:
            progress_callback(95, "Конвертация в PPTX…")
        return {"status": "completed", "progress": 100}

    def _create_plan(self, topic, slides_count, style, language,
                     include_charts, include_icons):
        system = "Ты — планировщик презентаций. Отвечай строго JSON без ```json."
        user = (
            f'Тема: "{topic}". Слайдов: {slides_count}, '
            f"стиль: {style}, язык: {language}.\n"
            f"Графики: {'да' if include_charts else 'нет'}, "
            f"Иконки: {'да' if include_icons else 'нет'}.\n"
            "Самостоятельно подбери цвета для темы, соответствующие стилю "
            f"«{style}» (например, для светлого — светлый фон, тёмный "
            "текст; для тёмного — тёмный фон, светлый текст).\n"
            "Верни JSON строго в формате:\n"
            "{\n"
            '  "theme": {\n'
            '    "colors": {\n'
            '      "primary": "#hex",\n'
            '      "accent": "#hex",\n'
            '      "bgLight": "#hex",\n'
            '      "textDark": "#hex",\n'
            '      "textLight": "#hex"\n'
            "    },\n"
            '    "textStyles": {\n'
            '      "title": { "fontSize": 36, "fontFamily": "Inter", "color": "$textLight" },\n'
            '      "subtitle": { "fontSize": 28, "fontFamily": "Inter", "color": "$textLight" },\n'
            '      "body": { "fontSize": 20, "fontFamily": "Inter", "color": "$textDark" },\n'
            '      "small": { "fontSize": 12, "fontFamily": "Inter", "color": "$textDark" }\n'
            "    }\n"
            "  },\n"
            f'  "pages": ["cover.page", ...]  // ровно {slides_count} имён\n'
            "}\n"
            "Ответ только JSON без каких-либо дополнительных символов."
        )
        resp = self.llm.chat([{"role": "system", "content": system},
                               {"role": "user", "content": user}],
                              temperature=0.2, max_tokens=800)

        # Разбор JSON (устойчивый)
        json_str = resp.strip()
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        start_brace = json_str.find("{")
        end_brace = json_str.rfind("}")
        if start_brace != -1 and end_brace != -1:
            json_str = json_str[start_brace:end_brace + 1]
        else:
            raise ValueError("Не удалось найти JSON в ответе планировщика")

        try:
            plan = json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"Ошибка парсинга JSON плана: {e}\nОтвет модели:\n{resp}")
            raise ValueError("План не является валидным JSON")

        # Контроль количества страниц
        planned_pages = plan.get("pages", [])
        if len(planned_pages) != slides_count:
            if len(planned_pages) < slides_count:
                planned_pages += [f"slide_{i}.page"
                                  for i in range(len(planned_pages), slides_count)]
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
            with open(pptd_files[0], "r", encoding="utf-8") as f:
                pptd = yaml.safe_load(f)
                theme = pptd.get("theme", {})
        with open(page_path, "r", encoding="utf-8") as f:
            current_yaml = f.read()
        role = LayoutTool.classify_role(page_name)
        gen = PageGenerator(self.llm, theme, self.icon_tool,
                            self.chart_tool, self.improver_tool)
        improved = gen.improve(page_name, current_yaml, instruction, role)
        with open(page_path, "w", encoding="utf-8") as f:
            yaml.dump(improved, f, allow_unicode=True)
        return improved