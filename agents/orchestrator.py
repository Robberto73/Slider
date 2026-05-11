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
from tools.polisher import PresentationPolisher


class OrchestratorAgent(PresentationAgent):
    def __init__(self, llm: BaseLLM, icons_dir: Path = None):
        self.llm = llm
        self.icon_tool = IconTool(icons_dir) if icons_dir else None
        self.chart_tool = ChartTool(llm=self.llm)
        self.improver_tool = PageImproverTool(llm)
        self.memory = PresentationMemory()

    # ═══════════════════════════════════════════════════════════
    # ГЛАВНЫЙ МЕТОД ГЕНЕРАЦИИ
    # ═══════════════════════════════════════════════════════════

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

        pages_content = PresentationPolisher.polish(pages_content, theme)
        self._save(theme, pages_content, output_dir)

        if progress_callback:
            progress_callback(95, "Конвертация в PPTX…")
        return {"status": "completed", "progress": 100}

    # ═══════════════════════════════════════════════════════════
    # ПЛАНИРОВАНИЕ С ЗАЩИТОЙ ОТ ОШИБОК
    # ═══════════════════════════════════════════════════════════

    def _create_plan(self, topic, slides_count, style, language,
                     include_charts, include_icons):
        theme = {
            "colors": {
                "primary": "#1E3330",
                "accent": "#C9892E",
                "bgLight": "#F0EDEA",
                "bgDark": "#1C2524",
                "textDark": "#1C2524",
                "textLight": "#F0EDEA",
                "cardBg": "#FFFFFF",
                "border": "#D5D0CA",
                "success": "#2E7D32",
                "warning": "#ED6C02",
                "danger": "#D32F2F"
            },
            "textStyles": {
                "title": {"fontSize": 44, "fontFamily": "Montserrat", "lineHeight": 1.2, "weight": "bold"},
                "subtitle": {"fontSize": 28, "fontFamily": "Montserrat", "lineHeight": 1.3, "weight": "medium"},
                "body": {"fontSize": 20, "fontFamily": "Inter", "lineHeight": 1.5, "weight": "regular"},
                "small": {"fontSize": 16, "fontFamily": "Inter", "lineHeight": 1.4, "weight": "regular"},
                "caption": {"fontSize": 14, "fontFamily": "Inter", "lineHeight": 1.3, "weight": "regular"},
                "metric": {"fontSize": 56, "fontFamily": "Montserrat", "lineHeight": 1.0, "weight": "bold"}
            },
            "fontPair": "Montserrat + Inter",
            "spacingScale": [8, 16, 24, 32, 48, 64, 96],  # базовые отступы
            "borderRadius": [0, 4, 8, 12, 16, 24],
            "shadows": {
                "card": "0 2px 8px rgba(0,0,0,0.08)",
                "elevated": "0 8px 24px rgba(0,0,0,0.12)"
            }
        }
        system = """Ты — стратегический планировщик презентаций McKinsey-уровня.
        Каждая презентация — это аргумент (story), а не набор слайдов.
        Структура: Ситуация → Проблема → Решение → Доказательства → Действие."""

        # Определяем story arc в зависимости от количества слайдов
        arc_templates = {
            5: ["hook", "problem", "solution", "proof", "cta"],
            7: ["cover", "agenda", "problem", "solution", "proof", "details", "cta"],
            10: ["cover", "agenda", "context", "problem", "solution_overview",
                 "solution_details", "proof_data", "proof_cases", "risks", "cta"],
            15: ["cover", "agenda", "executive_summary", "market_context",
                 "problem_deep", "solution_vision", "solution_architecture",
                 "solution_features", "data_evidence", "case_studies",
                 "competitive", "implementation", "team", "financials", "cta"]
        }

        # Ближайший шаблон
        target_arc = arc_templates.get(slides_count, arc_templates[7])
        if slides_count > 15:
            # Расширяем базовый 15-слайдовый
            target_arc = arc_templates[15] + [f"detail_{i}" for i in range(slides_count - 15)]

        user = (
            f'Тема: "{topic}"\n'
            f'Слайдов: {slides_count}, стиль: {style}, язык: {language}.\n'
            f'Графики: {"да" if include_charts else "нет"}, '
            f'Иконки: {"да" if include_icons else "нет"}.\n\n'
            f'Нарративная структура ({len(target_arc)} слайдов):\n'
            f'{", ".join(target_arc)}\n\n'
            f'Для КАЖДОГО слайда укажи:\n'
            f'- name: имя файла (например, 01_cover.page)\n'
            f'- title: заголовок, который ПРОДАЁТ идею (не описывает, а убеждает)\n'
            f'- role: из списка: cover, agenda, title_and_content, two_content, '
            f'content_with_chart, content_with_table, conclusion, quote, timeline, comparison\n'
            f'- narrative_purpose: зачем этот слайд в истории (1 предложение)\n'
            f'- key_message: главная мысль, которую зритель должен унести\n'
            f'- bullets: 3-5 тезисов, каждый — максимум 12 слов, начинается с глагола\n'
            f'- icon_ideas: 2-3 иконки, которые визуально усилят сообщение\n'
            f'- chart_suggestion: если уместно — тип данных и инсайт, который график покажет\n'
            f'- emotional_tone: formal / inspiring / urgent / calm / provocative\n'
            f'\nТакже предложи тему (colors, textStyles, fontPair).\n'
            f'fontPair — пара шрифтов: заголовочный и текстовый (например, "Montserrat + Inter")\n'
            f'\nОтвет ТОЛЬКО JSON. Без комментариев.'
        )



        # Пробуем до 3 раз с понижением температуры
        for attempt in range(3):
            temp = max(0.1, 0.5 - attempt * 0.15)
            try:
                resp = self.llm.chat(
                    [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
                    temperature=temp,
                    max_tokens=2000
                )



                plan = self._parse_plan_response(resp, slides_count, style)
                if isinstance(plan, dict) and "pages" in plan:
                    return plan
            except Exception as e:
                print(f"⚠ Попытка {attempt+1} планирования не удалась: {e}")

        # Все попытки провалились — fallback
        return self._default_plan(topic, slides_count, style)

    def _parse_plan_response(self, resp, slides_count, style):
        """Парсит ответ LLM в план с защитой от ошибок."""
        if not isinstance(resp, str):
            resp = str(resp) if resp else "{}"

        json_str = resp.strip()

        # Убираем markdown
        for prefix in ["```json", "```yaml", "```"]:
            if json_str.startswith(prefix):
                json_str = json_str[len(prefix):]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        json_str = json_str.strip()

        # Ищем JSON
        start_brace = json_str.find("{")
        end_brace = json_str.rfind("}")
        if start_brace == -1 or end_brace == -1 or end_brace <= start_brace:
            raise ValueError("JSON не найден в ответе")

        json_str = json_str[start_brace:end_brace + 1]

        try:
            plan = json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"⚠ Ошибка парсинга JSON: {e}\nТекст: {json_str[:500]}")
            raise ValueError("План не является валидным JSON")

        # Защита: проверяем структуру
        if not isinstance(plan, dict):
            raise ValueError("Распарсенный план не словарь")

        if "pages" not in plan or not isinstance(plan.get("pages"), list):
            plan["pages"] = []

        # Дозаполняем до нужного количества
        detailed_pages = plan["pages"]
        while len(detailed_pages) < slides_count:
            detailed_pages.append({
                "name": f"slide_{len(detailed_pages)}.page",
                "title": f"Слайд {len(detailed_pages)+1}",
                "role": "title_and_content",
                "bullets": [],
                "icon_ideas": [],
                "chart_suggestion": None
            })
        plan["pages"] = detailed_pages[:slides_count]

        # Защита: theme
        if "theme" not in plan or not isinstance(plan.get("theme"), dict):
            plan["theme"] = self._default_theme(style)

        return plan

    def _default_plan(self, topic, slides_count, style):
        """Гарантированный план при провале LLM."""
        return {
            "theme": self._default_theme(style),
            "pages": [
                {
                    "name": f"{i:02d}_slide.page",
                    "title": f"Слайд {i+1}",
                    "role": "title_and_content",
                    "bullets": [f"Пункт {j+1} для темы: {topic[:50]}" for j in range(3)],
                    "icon_ideas": ["circle"],
                    "chart_suggestion": None
                }
                for i in range(slides_count)
            ]
        }

    def _default_theme(self, style):
        """Дефолтная тема."""
        is_dark = style == "dark"
        return {
            "colors": {
                "primary": "#1E3330",
                "accent": "#C9892E",
                "bgLight": "#1C2524" if is_dark else "#F0EDEA",
                "bgDark": "#1C2524",
                "textDark": "#F0EDEA" if is_dark else "#1C2524",
                "textLight": "#F0EDEA",
                "cardBg": "#2A3F3C" if is_dark else "#FFFFFF",
                "border": "#D5D0CA"
            },
            "textStyles": {
                "title": {"fontSize": 44, "fontFamily": "Arial", "lineHeight": 1.2},
                "subtitle": {"fontSize": 28, "fontFamily": "Arial", "lineHeight": 1.3},
                "body": {"fontSize": 20, "fontFamily": "Arial", "lineHeight": 1.5},
                "small": {"fontSize": 16, "fontFamily": "Arial", "lineHeight": 1.4}
            },
            "tableStyles": {
                "default": {
                    "headerFill": "$primary",
                    "headerColor": "$textLight",
                    "bodyFill": ["$bgLight", "$cardBg"],
                    "bodyColor": "$textDark",
                    "fontSize": 16,
                    "fontFamily": "Arial"
                }
            }
        }

    # ═══════════════════════════════════════════════════════════
    # РЕФЛЕКСИВНОЕ УЛУЧШЕНИЕ (переработано)
    # ═══════════════════════════════════════════════════════════

    def _auto_improve_presentation(self, pages_content: Dict[str, Any], theme: Dict,
                                   topic: str, style: str, language: str,
                                   include_charts: bool, include_icons: bool) -> Dict[str, Any]:
        """Проверяет качество и улучшает слайды с конкретной диагностикой."""
        gen = PageGenerator(self.llm, theme, self.icon_tool, self.chart_tool)
        improved_pages = dict(pages_content)

        # Фаза 1: Быстрая оценка всех слайдов
        scores = {}
        issues_map = {}
        for page_name, content in pages_content.items():
            role = LayoutTool.classify_role(page_name)
            score = gen._evaluate_page_fast(content, role)
            scores[page_name] = score
            issues_map[page_name] = self._diagnose_issues(content, role)

        # Фаза 2: Определяем слайды для улучшения
        low_quality = [
            (name, content, scores[name], issues_map[name])
            for name, content in pages_content.items()
            if scores[name] < 6
        ]

        if not low_quality:
            return improved_pages

        # Фаза 3: Улучшение с конкретными инструкциями
        max_improvements = max(1, len(pages_content) // 3)

        for page_name, content, score, page_issues in low_quality[:max_improvements]:
            role = LayoutTool.classify_role(page_name)

            # Формируем конкретную инструкцию
            fix_instructions = self._build_fix_prompt(page_issues, role)
            memory_context = self.memory.get_context_for_next_slide()

            extra = (
                f"ИСПРАВЛЕНИЕ СЛАЙДА (текущая оценка: {score}/10).\n"
                f"Конкретные проблемы:\n{fix_instructions}\n\n"
                f"Контекст презентации:\n{memory_context}\n\n"
                f"Тема: {topic}. Стиль: {style}. Язык: {language}."
            )

            # Генерируем исправленную версию
            improved = gen.generate(
                page_name, topic, style, language,
                include_charts, include_icons, extra, role
            )

            # Фаза 4: Проверяем, стало ли лучше
            new_score = gen._evaluate_page_fast(improved, role)
            if new_score > score:
                improved_pages[page_name] = improved
                title = self._extract_title(improved)
                icons = self._extract_icons(improved)
                self.memory.add_slide(page_name, title, icons)
            else:
                # Fallback-шаблон, если LLM не справился
                fallback = self._apply_fallback_template(role, theme, content)
                fallback_score = gen._evaluate_page_fast(fallback, role)
                if fallback_score > score:
                    improved_pages[page_name] = fallback

        return improved_pages

    def _diagnose_issues(self, content: Dict, role: SlideRole) -> List[str]:
        """Диагностирует конкретные проблемы слайда."""
        issues = []
        elements = content.get("elements", [])
        texts = [e for e in elements if e.get("elementType") == "text"]

        if not elements:
            issues.append("Слайд полностью пуст — нет ни одного элемента")
            return issues

        if not texts:
            issues.append("Нет текстовых элементов")
        else:
            empty_count = sum(
                1 for t in texts
                if not t.get("content", {}).get("text", "").strip()
            )
            if empty_count == len(texts):
                issues.append("Все текстовые блоки пусты")
            elif empty_count > 0:
                issues.append(f"{empty_count} текстовых блоков пусты")

        has_title = any(
            t.get("content", {}).get("style", "") == "$title"
            for t in texts
        )
        if not has_title and role != SlideRole.BLANK:
            issues.append("Отсутствует заголовок слайда")

        bg = content.get("background", {})
        if bg.get("type") == "solid" and bg.get("color") == "$primary":
            issues.append("Фон слайда чёрный — возможно, ошибка генерации")

        overlaps = self._count_overlaps(elements)
        if overlaps > 0:
            issues.append(f"{overlaps} пар элементов перекрываются")

        return issues

    def _count_overlaps(self, elements: List[Dict]) -> int:
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

    def _build_fix_prompt(self, issues: List[str], role: SlideRole) -> str:
        """Строит промпт для исправления на основе диагностики."""
        fixes = []
        for issue in issues:
            if "пуст" in issue.lower():
                fixes.append("- Добавь осмысленный контент во все текстовые блоки")
            if "заголовок" in issue.lower():
                fixes.append("- Добавь чёткий заголовок слайда (style: $title)")
            if "чёрный" in issue.lower():
                fixes.append("- Используй светлый фон (color: $bgLight) вместо чёрного")
            if "перекрываются" in issue.lower():
                fixes.append("- Разнеси элементы, чтобы не накладывались друг на друга")

        role_fixes = {
            SlideRole.COVER: "Это титульный слайд: нужен крупный заголовок и подзаголовок",
            SlideRole.CONTENT_WITH_CHART: "Добавь реалистичные данные для графика",
            SlideRole.CONCLUSION: "Добавь итоговые тезисы и призыв к действию",
        }
        if role in role_fixes:
            fixes.append(f"- {role_fixes[role]}")

        return "\n".join(fixes)

    def _apply_fallback_template(self, role: SlideRole, theme: Dict,
                                  original: Dict) -> Dict:
        """Применяет гарантированный шаблон при провале LLM."""
        colors = theme.get("colors", {})
        bg = colors.get("bgLight", "$bgLight")
        text = colors.get("textDark", "$textDark")

        # Извлекаем заголовок из оригинала, если есть
        original_title = "Заголовок слайда"
        for el in original.get("elements", []):
            if el.get("elementType") == "text":
                style = el.get("content", {}).get("style", "")
                if "title" in style:
                    original_title = el.get("content", {}).get("text", original_title)
                    break

        templates = {
            SlideRole.COVER: {
                "background": {"type": "solid", "color": bg},
                "elements": [
                    {
                        "elementType": "text",
                        "bounds": [200, 300, 1520, 200],
                        "content": {
                            "text": original_title,
                            "style": "$title",
                            "align": ["center", "middle"],
                            "color": text
                        }
                    },
                    {
                        "elementType": "text",
                        "bounds": [200, 520, 1520, 120],
                        "content": {
                            "text": "Подзаголовок презентации",
                            "style": "$subtitle",
                            "align": ["center", "middle"],
                            "color": text
                        }
                    }
                ]
            },
            SlideRole.TITLE_AND_CONTENT: {
                "background": {"type": "solid", "color": bg},
                "elements": [
                    {
                        "elementType": "text",
                        "bounds": [120, 80, 1680, 120],
                        "content": {
                            "text": original_title,
                            "style": "$title",
                            "align": ["left", "middle"],
                            "color": text
                        }
                    },
                    {
                        "elementType": "text",
                        "bounds": [120, 240, 1680, 600],
                        "content": {
                            "text": "Основное содержание слайда. Добавьте ключевые тезисы и данные.",
                            "style": "$body",
                            "align": ["left", "top"],
                            "color": text
                        }
                    }
                ]
            },
            SlideRole.CONTENT_WITH_CHART: {
                "background": {"type": "solid", "color": bg},
                "elements": [
                    {
                        "elementType": "text",
                        "bounds": [120, 80, 1680, 120],
                        "content": {
                            "text": original_title,
                            "style": "$title",
                            "align": ["left", "middle"],
                            "color": text
                        }
                    },
                    {
                        "elementType": "chart",
                        "bounds": [120, 240, 1200, 700],
                        "type": "bar",
                        "data": [
                            {"категория": "Категория 1", "значение": 25},
                            {"категория": "Категория 2", "значение": 40},
                            {"категория": "Категория 3", "значение": 35},
                        ],
                        "colors": ["$accent", "$primary", "$textLight"]
                    }
                ]
            },
            SlideRole.CONCLUSION: {
                "background": {"type": "solid", "color": bg},
                "elements": [
                    {
                        "elementType": "text",
                        "bounds": [200, 300, 1520, 200],
                        "content": {
                            "text": original_title,
                            "style": "$title",
                            "align": ["center", "middle"],
                            "color": text
                        }
                    },
                    {
                        "elementType": "text",
                        "bounds": [200, 520, 1520, 300],
                        "content": {
                            "text": "Итоговые выводы и рекомендации.",
                            "style": "$body",
                            "align": ["center", "top"],
                            "color": text
                        }
                    }
                ]
            }
        }

        return templates.get(role, templates[SlideRole.TITLE_AND_CONTENT])

    # ═══════════════════════════════════════════════════════════
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ═══════════════════════════════════════════════════════════

    def _extract_title(self, page: Dict) -> str:
        for el in page.get("elements", []):
            if el.get("elementType") == "text":
                style = el.get("content", {}).get("style", "")
                if "title" in style:
                    return el.get("content", {}).get("text", "")
        return ""

    def _extract_icons(self, page: Dict) -> List[str]:
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