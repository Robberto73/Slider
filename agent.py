"""
Модуль агентов генерации презентаций.
Поддерживает две модели: локальную OpenAI-совместимую и GigaChat.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod
from openai import OpenAI


class PresentationAgent(ABC):
    """Абстрактный агент, генерирующий .pptd и .page файлы."""

    @abstractmethod
    def generate(self, topic: str, slides_count: int, style: str,
                 language: str, include_charts: bool, include_icons: bool,
                 output_dir: Path) -> Dict[str, Any]:
        pass


class LocalOpenAIAgent(PresentationAgent):
    """Отправляет запросы к локальной LLM с OpenAI API."""

    def __init__(self, base_url: str = "http://localhost:5000/v1", api_key: str = "not-needed"):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = self._detect_model()

    def _detect_model(self) -> str:
        try:
            models = self.client.models.list()
            if models.data:
                return models.data[0].id
        except Exception:
            pass
        return "local-model"

    def generate(self, topic: str, slides_count: int, style: str,
                 language: str, include_charts: bool, include_icons: bool,
                 output_dir: Path) -> Dict[str, Any]:

        prompt = self._build_prompt(topic, slides_count, style, language,
                                    include_charts, include_icons)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=4000
        )
        content = response.choices[0].message.content
        return self._parse_and_save(content, output_dir)

    def _build_prompt(self, topic, slides_count, style, language, include_charts, include_icons):
        include_charts_str = 'Включи графики (chart элементы) с реалистичными данными.' if include_charts else ''
        include_icons_str = 'Включи иконки Phosphor (icon элементы).' if include_icons else ''
        return f"""
Ты — генератор презентаций в формате Kimi PPTD (YAML). Создай презентацию на тему: "{topic}" ({language}).
Количество слайдов: {slides_count}, стиль: {style}.
{include_charts_str}
{include_icons_str}

Верни ОДИН валидный YAML-документ, который содержит:
- theme (colors, textStyles)
- pages (список имён .page файлов)
- для каждого .page файла отдельный ключ верхнего уровня с его содержимым.

Обязательные правила:
- Все цвета указывай со знаком $ (например, $primary, $accent, $textLight).
- Для иконок используй поле iconName (без расширения).
- Для графиков указывай тип (bar, pie, line) и данные (список словарей).
- Каждый элемент (text, shape, chart, icon) должен содержать bounds: [x, y, width, height] в пикселях (слайд 1920x1080).
- Текст оформляй в HTML-подобном виде: при необходимости выделяй <b>жирным</b> или <i>курсивом</i>.

Пример (сокращённый):

```yaml
theme:
  colors:
    primary: "#1E3330"
    accent: "#C9892E"
    bgLight: "#F0EDEA"
    textDark: "#1C2524"
    textLight: "#E8ECEB"
  textStyles:
    title:
      fontSize: 36
      fontFamily: Inter
      color: "$textLight"
    body:
      fontSize: 18
      fontFamily: Inter
      color: "$textDark"
pages:
  - cover.page
  - problems.page
cover.page:
  background:
    type: solid
    color: "$primary"
  elements:
    - elementType: text
      bounds: [100, 200, 1720, 400]
      content:
        text: "Заголовок презентации"
        style: "$title"
        align: [center, middle]
    - elementType: icon
      iconName: "shield"
      bounds: [860, 600, 200, 200]
problems.page:
  background:
    type: solid
    color: "$bgLight"
  elements:
    - elementType: chart
      type: bar
      data:
        - {{"категория": "А", "значение": 34}}
        - {{"категория": "Б", "значение": 56}}
      colors: ["$accent", "$secondary"]
      bounds: [200, 300, 1520, 700]
Теперь сгенерируй полный YAML для указанной темы. Ответ должен начинаться с yaml и заканчиваться.
"""

    def _parse_and_save(self, yaml_text: str, output_dir: Path) -> Dict[str, Any]:
        # Удаляем всё до первого ```yaml и после последнего ```
        start_marker = "```yaml"
        start = yaml_text.find(start_marker)
        if start != -1:
            yaml_text = yaml_text[start + len(start_marker):]
        else:
            # Если маркера нет, ищем просто ```
            start = yaml_text.find("```")
            if start != -1:
                yaml_text = yaml_text[start + 3:]

        # Удаляем закрывающий ``` (последнее вхождение)
        end = yaml_text.rfind("```")
        if end != -1:
            yaml_text = yaml_text[:end]

        # Убираем возможные оставшиеся обратные кавычки по краям и экранирования
        yaml_text = yaml_text.strip().strip("`").replace("\\`", "")

        if not yaml_text:
            raise ValueError("Пустой YAML после извлечения")

        try:
            data = yaml.safe_load(yaml_text)
            if not isinstance(data, dict):
                raise ValueError("Результат YAML не является словарём")
        except yaml.YAMLError as e:
            # Для отладки можно записать проблемный текст в лог
            import logging
            logging.error(f"Ошибка парсинга YAML: {e}\nТекст:\n{yaml_text[:500]}")
            raise ValueError(f"Ошибка парсинга YAML: {e}")

        theme = data.get("theme", {})
        page_list = data.get("pages", [])
        if not page_list:
            raise ValueError("В ответе модели нет списка pages")

        # Сохраняем .pptd
        pptd = {"theme": theme, "pages": page_list}
        with open(output_dir / "presentation.pptd", "w", encoding="utf-8") as f:
            yaml.dump(pptd, f, allow_unicode=True)

        # Сохраняем .page файлы
        pages_dir = output_dir / "pages"
        pages_dir.mkdir(exist_ok=True)
        saved_count = 0
        for key, value in data.items():
            if key.endswith(".page") and isinstance(value, dict):
                page_path = pages_dir / key
                with open(page_path, "w", encoding="utf-8") as f:
                    yaml.dump(value, f, allow_unicode=True)
                saved_count += 1

        if saved_count == 0:
            raise ValueError("Не найдено ни одного .page файла в ответе модели")

        return {"status": "completed", "progress": 100}

class GigaChatAgent(PresentationAgent):
    """Использует GigaChat API для генерации."""
    def init(self, api_key: Optional[str] = None, base_url: str = "https://gigachat.devices.sberbank.ru/api/v1"):
        self.api_key = api_key or os.environ.get("GIGACHAT_API_KEY")
        if not self.api_key:
            raise ValueError("Не задан GIGACHAT_API_KEY")
        self.base_url = base_url
        self.client = OpenAI(base_url=self.base_url, api_key=self.api_key)

    def generate(self, topic: str, slides_count: int, style: str,
        language: str, include_charts: bool, include_icons: bool,
        output_dir: Path) -> Dict[str, Any]:
        prompt = LocalOpenAIAgent._build_prompt(None, topic, slides_count, style, language,
        include_charts, include_icons)
        response = self.client.chat.completions.create(
            model="GigaChat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=4000
        )
        content = response.choices[0].message.content
        return LocalOpenAIAgent._parse_and_save(None, content, output_dir)

def create_agent(model_type: str, **kwargs) -> PresentationAgent:
    if model_type == "local":
        base_url = kwargs.get("local_base_url", "http://localhost:5000/v1")
        return LocalOpenAIAgent(base_url=base_url)
    elif model_type == "gigachat":
        api_key = kwargs.get("gigachat_api_key") or os.environ.get("GIGACHAT_API_KEY")
        return GigaChatAgent(api_key=api_key)
    else:
        raise ValueError(f"Неизвестный тип модели: {model_type}")