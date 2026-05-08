"""
Инструмент улучшения страницы: принимает текущий YAML, описание желаемых изменений и возвращает улучшенный YAML.
"""

import yaml
import json
from typing import Dict, Any, Optional
from agents.base import BaseLLM


class PageImproverTool:
    def __init__(self, llm: BaseLLM):
        self.llm = llm

    def improve(self, current_yaml: str, instruction: str, theme: Dict, page_name: str) -> Dict[str, Any]:
        """
        Возвращает улучшенный словарь страницы.
        current_yaml - текущий YAML страницы (строка)
        instruction - пользовательское описание изменений
        theme - словарь темы презентации
        """
        system = self._build_system_prompt(theme)
        user = f"""Текущее содержимое страницы {page_name}:
```yaml
{current_yaml}
Инструкция по улучшению: {instruction}

Улучши страницу строго по инструкции, сохраняя корректный формат Kimi PPTD.
Ответь ТОЛЬКО новым YAML без ```, который можно сразу сохранить как .page файл.
"""
        messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user}
        ]
        response = self.llm.chat(messages, temperature=0.2, max_tokens=1500)
        try:
            new_data = yaml.safe_load(response)
            if not isinstance(new_data, dict):
                raise ValueError("Модель вернула не словарь")
            return new_data
        except Exception as e:
            #fallback: попробуем извлечь из текста
            raise ValueError(f"Ошибка парсинга улучшенного YAML: {e}")

    def _build_system_prompt(self, theme: Dict) -> str:
        return f"""Ты — инструмент улучшения слайда презентации Kimi PPTD.
Ты получаешь текущий YAML слайда и инструкцию по улучшению.
Ты должен вернуть ТОЛЬКО YAML слайда после улучшения (без ```).
Тема презентации: {json.dumps(theme, ensure_ascii=False)}
Формат слайда строго как в Kimi PPTD:
background:
type: solid | image
color: "$primary" (или другой из theme)
elements:

elementType: text | shape | icon | chart
bounds: [x, y, width, height] # пиксели, слайд 1920x1080
(специфичные поля)
"""