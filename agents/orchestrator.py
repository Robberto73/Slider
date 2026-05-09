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
from tools.presentation_memory import PresentationMemory

class OrchestratorAgent(PresentationAgent):
    def __init__(self, llm: BaseLLM, icons_dir: Path = None):
        self.llm = llm
        self.icon_tool = IconTool(icons_dir) if icons_dir else None
        self.chart_tool = ChartTool(llm=self.llm)
        self.improver_tool = PageImproverTool(llm)
        self.memory = PresentationMemory()

    def generate(self, topic, slides_count, style, language,
                 include_charts, include_icons, output_dir, progress_callback=None):
        if progress_callback:
            progress_callback(5, "Планирование структуры…")

        plan = self._create_plan(topic, slides_count, style, language,
                                 include_charts, include_icons)
        theme = plan["theme"]
        pages: List[Dict] = plan["pages"]

        gen = PageGenerator(self.llm, theme, self.icon_tool, self.chart_tool)
        pages_content: Dict[str, Any] = {}

        for i, page_info in enumerate(pages):
            page_name = page_info["name"]
            pct = 5 + int((i / len(pages)) * 80)
            if progress_callback:
                progress_callback(pct, f"Генерация слайда {i+1} из {len(pages)}: {page_name}")

            role = LayoutTool.classify_role(page_name)
            memory_context = self.memory.get_context_for_next_slide()
            extra = (
                f"Страница {i+1} из {len(pages)}. "
                f"Роль: {role.value}. "
                f"Заголовок: {page_info.get('title', '')}. "
                f"Пункты: {json.dumps(page_info.get('bullets', []), ensure_ascii=False)}. "
                f"Идеи иконок: {page_info.get('icon_ideas', [])}. "
                f"График: {page_info.get('chart_suggestion')}. "
                f"Тема: {topic}. "
                f"Стиль: {style}. Язык: {language}.\n\n"
                f"КОНТЕКСТ ПРЕЗЕНТАЦИИ:\n{memory_context}\n\n"
                f"Не повторяй уже использованные заголовки и иконки. Сохраняй уникальность."
            )
            content = gen.generate(page_name, topic, style, language,
                                   include_charts, include_icons, extra, role)
            pages_content[page_name] = content

            # Запоминаем заголовок и иконки этого слайда
            title = self._extract_title(content)
            icons = self._extract_icons(content)
            self.memory.add_slide(page_name, title, icons)

        # Адаптивное улучшение: проверяем качество всей презентации
        if progress_callback:
            progress_callback(85, "Анализ качества презентации…")

        pages_content = self._auto_improve_presentation(pages_content, theme, topic, style, language,
                                                        include_charts, include_icons)

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
            f'Запрос пользователя:\n{topic}\n\n'
            f'Слайдов: {slides_count}, стиль: {style}, язык: {language}.\n'
            f'Графики: {"да" if include_charts else "нет"}, '
            f'Иконки: {"да" if include_icons else "нет"}.\n'
            'Составь ДЕТАЛЬНЫЙ план каждого слайда как массив объектов JSON.\n'
            'Для каждого слайда укажи:\n'
            '- name: имя файла (например, cover.page)\n'
            '- title: краткий заголовок слайда\n'
            '- role: одна из ролей: cover, content_with_icons, content_with_chart, conclusion, title_and_content\n'
            '- bullets: список строк — основные пункты, которые нужно раскрыть на слайде\n'
            '- icon_ideas: список строк — идей иконок (например, «щит», «карта»), которые подойдут к этому слайду\n'
            '- chart_suggestion: если нужен график, укажи тип (bar/pie/line) и какие данные показать, иначе null\n'
            'Также предложи тему (colors, textStyles) как раньше.\n'
            'Формат ответа:\n'
            '{\n'
            '  "theme": { ... },\n'
            '  "pages": [\n'
            '    {\n'
            '      "name": "cover.page",\n'
            '      "title": "GeoIP Intelligence",\n'
            '      "role": "cover",\n'
            '      "bullets": ["Подзаголовок: R&D исследование"],\n'
            '      "icon_ideas": ["шит"],\n'
            '      "chart_suggestion": null\n'
            '    },\n'
            '    ...\n'
            '  ]\n'
            '}\n'
            'Ответ ТОЛЬКО JSON, без дополнительного текста.'
        )
        resp = self.llm.chat([{"role": "system", "content": system},
                               {"role": "user", "content": user}],
                              temperature=0.3, max_tokens=1500)

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

        detailed_pages = plan.get("pages", [])
        if len(detailed_pages) != slides_count:
            if len(detailed_pages) < slides_count:
                detailed_pages += [
                    {"name": f"slide_{i}.page", "title": f"Слайд {i}", "role": "title_and_content",
                     "bullets": [], "icon_ideas": [], "chart_suggestion": None}
                    for i in range(len(detailed_pages), slides_count)
                ]
            else:
                detailed_pages = detailed_pages[:slides_count]
            plan["pages"] = detailed_pages

        return plan

    def _extract_title(self, page: Dict) -> str:
        """Извлекает заголовок из сгенерированного слайда."""
        for el in page.get("elements", []):
            if el.get("elementType") == "text":
                style = el.get("content", {}).get("style", "")
                if "title" in style:
                    return el.get("content", {}).get("text", "")
        return ""

    def _extract_icons(self, page: Dict) -> List[str]:
        """Извлекает имена иконок из слайда."""
        icons = []
        for el in page.get("elements", []):
            if el.get("elementType") == "icon":
                name = el.get("iconName", "")
                if isinstance(name, str):
                    icons.append(name)
        return icons

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

    def _auto_improve_presentation(self, pages_content: Dict[str, Any], theme: Dict, topic: str, style: str,
                                   language: str, include_charts: bool, include_icons: bool) -> Dict[str, Any]:
        """Проверяет качество всей презентации и улучшает слайды с низкой оценкой."""
        gen = PageGenerator(self.llm, theme, self.icon_tool, self.chart_tool)
        low_quality_pages = []

        # Оцениваем каждый слайд
        for page_name, content in pages_content.items():
            score = gen._evaluate_page(content, LayoutTool.classify_role(page_name))
            if score < 7:  # Порог качества
                low_quality_pages.append((page_name, content, score))

        if not low_quality_pages:
            return pages_content

        # Улучшаем по одному слайду за раз, максимум 40% от общего числа
        max_improvements = max(1, len(pages_content) // 3)
        for page_name, content, score in low_quality_pages[:max_improvements]:
            role = LayoutTool.classify_role(page_name)
            memory_context = self.memory.get_context_for_next_slide()
            extra = (
                f"Улучши этот слайд. Его текущая оценка качества: {score}/10. "
                f"Контекст презентации:\n{memory_context}\n"
                f"Сделай его более наполненным, визуально привлекательным и соответствующим теме."
            )
            improved_content = gen.generate(page_name, topic, style, language,
                                            include_charts, include_icons, extra, role)
            pages_content[page_name] = improved_content

            # Обновляем память о слайде
            title = self._extract_title(improved_content)
            icons = self._extract_icons(improved_content)
            self.memory.add_slide(page_name, title, icons)

        return pages_content