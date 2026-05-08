from typing import List, Dict, Any
import random

class ChartTool:
    """Генерирует правдоподобные данные для графиков без вызова LLM (можно заменить на вызов)."""
    @staticmethod
    def generate(chart_type: str, topic: str, count: int = 4) -> List[Dict[str, Any]]:
        """Возвращает список словарей, совместимый с элементом chart."""
        # Заглушка: создаём категории на основе темы и случайные положительные числа
        categories = [f"{topic[:10]}_{i}" for i in range(count)]
        values = [round(random.uniform(10, 200), 1) for _ in range(count)]
        return [{"категория": c, "значение": v} for c, v in zip(categories, values)]