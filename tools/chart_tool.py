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

    def _llm_labels(self, topic: str, count: int) -> List[str]:
        """Запрашивает у LLM список релевантных категорий."""
        prompt = (
            f"Для темы \"{topic}\" придумай {count} коротких названий категорий "
            f"для графика. Верни ТОЛЬКО список строк через запятую, без кавычек. "
            f"Пример: Москва, Санкт-Петербург, Казань"
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

    def _generate_values(self, count: int, topic: str) -> List[float]:
        """Генерирует правдоподобные числа (с трендом, если в теме есть ключевые слова)."""
        base = [round(random.uniform(10, 300), 1) for _ in range(count)]
        # Если тема про рост/падение – делаем тренд
        if any(w in topic.lower() for w in ("рост", "увеличение", "повышение")):
            base.sort()
        elif any(w in topic.lower() for w in ("падение", "снижение", "уменьшение")):
            base.sort(reverse=True)
        return base