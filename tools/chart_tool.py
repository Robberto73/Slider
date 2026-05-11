# tools/chart_tool.py
import random
import re
from typing import List, Dict, Any, Optional

class ChartTool:
    def __init__(self, llm=None):
        self.llm = llm  # может использоваться только для получения названий категорий

    def generate(self, chart_type: str, topic: str, count: int = 4,
                 use_llm_for_labels: bool = True) -> List[Dict[str, Any]]:
        """
        Генерирует данные для графика.
        - Названия категорий: из темы (ключевые слова) или через LLM.
        - Числовые значения: случайные, с возможным трендом.
        """
        # 1. Получаем названия категорий
        if self.llm and use_llm_for_labels:
            labels = self._llm_labels(topic, count)
        else:
            labels = self._keyword_labels(topic, count)

        # 2. Генерируем значения
        values = self._generate_values(count, topic)

        # 3. Объединяем
        return [{"категория": label, "значение": val} for label, val in zip(labels, values)]

    def _keyword_labels(self, topic: str, count: int) -> List[str]:
        """Извлекает ключевые слова из темы."""
        # Убираем короткие и стоп-слова
        words = re.findall(r'\b\w{4,}\b', topic)
        # Оставляем только существительные (по первой заглавной? но для русского сложно)
        # Просто берём самые длинные слова, или добавляем обобщённые
        labels = []
        for w in words:
            if w.lower() not in ("это", "для", "как", "что", "или", "при"):
                labels.append(w.capitalize())
        # Если мало, добавляем шаблонные
        while len(labels) < count:
            labels.append(f"Категория {len(labels)+1}")
        return labels[:count]

    def _llm_labels(self, topic: str, count: int, context: str = "") -> List[str]:
        """Умные метки с контекстом."""
        prompt = (
            f"Тема презентации: '{topic}'\n"
            f"Контекст слайда: {context}\n"
            f"Придумай {count} коротких названий категорий для графика. "
            f"Они должны быть:\n"
            f"- Релевантны теме (не абстрактные 'Категория 1')\n"
            f"- Разной длины (2-4 слова)\n"
            f"- Содержать конкретику (годы, регионы, продукты)\n"
            f"Верни ТОЛЬКО список через запятую."
        )
        try:
            resp = self.llm.chat([{"role": "user", "content": prompt}],
                                 temperature=0.7, max_tokens=100)
            # Разбираем ответ
            labels = [s.strip() for s in resp.split(",") if s.strip()]
            while len(labels) < count:
                labels.append(f"Кат.{len(labels)+1}")
            return labels[:count]
        except Exception:
            return self._keyword_labels(topic, count)

    def _generate_values(self, count: int, topic: str, trend: str = None) -> List[float]:
        """Генерирует правдоподобные числа с учётом контекста темы."""
        # Определяем масштаб из темы
        if any(w in topic.lower() for w in ("миллиард", "billion", "млрд")):
            base_scale = 1_000_000_000
        elif any(w in topic.lower() for w in ("миллион", "million", "млн")):
            base_scale = 1_000_000
        elif any(w in topic.lower() for w in ("процент", "%", "percent")):
            base_scale = 100
        else:
            base_scale = 1000

        # Генерируем с трендом
        if trend == "growth":
            values = [base_scale * (0.5 + i * 0.3 + random.uniform(-0.1, 0.1)) for i in range(count)]
        elif trend == "decline":
            values = [base_scale * (2.0 - i * 0.4 + random.uniform(-0.1, 0.1)) for i in range(count)]
        elif trend == "volatile":
            values = [base_scale * random.uniform(0.3, 2.0) for _ in range(count)]
        else:  # stable
            values = [base_scale * random.uniform(0.8, 1.2) for _ in range(count)]

        return [round(v, 1) for v in values]