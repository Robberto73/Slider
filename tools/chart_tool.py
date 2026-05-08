import random
from typing import List, Dict, Any

# Современные палитры (можно расширять)
PALETTES = {
    "business": ["#2E86AB", "#A23B72", "#F18F01", "#C73E1D", "#6B7D7B"],
    "cyber": ["#00F0FF", "#FF007F", "#7B2D8E", "#00FF7F", "#FFD700"],
    "nature": ["#2D6A4F", "#52B788", "#D4EDDA", "#FFB703", "#FB8500"],
}

class ChartTool:
    @staticmethod
    def generate(chart_type: str, topic: str, count: int = 4, palette: str = "business") -> List[Dict[str, Any]]:
        # Определяем ключевые слова из темы для категорий
        keywords = [w.strip() for w in topic.split() if len(w) > 3][:count]
        if len(keywords) < count:
            keywords = [f"Точка {i+1}" for i in range(count)]

        # Генерируем значения (контекстно? можно усложнить с LLM, пока просто)
        values = [round(random.uniform(10, 300), 1) for _ in range(count)]
        # Если тема содержит "рост" или "падение" – тренд
        if "рост" in topic.lower() or "увеличение" in topic.lower():
            values.sort()
        elif "падение" in topic.lower() or "снижение" in topic.lower():
            values.sort(reverse=True)

        colors = PALETTES.get(palette, PALETTES["business"])
        return [
            {"категория": kw, "значение": val, "color": colors[i % len(colors)]}
            for i, (kw, val) in enumerate(zip(keywords, values))
        ]