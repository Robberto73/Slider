"""
Память презентации. Отслеживает использованные заголовки и иконки,
чтобы агент не повторялся и соблюдал уникальность.
"""

from typing import List, Set
from collections import defaultdict


class PresentationMemory:
    def __init__(self):
        self.used_titles: Set[str] = set()
        self.used_icons: Set[str] = set()
        self.slide_history: List[dict] = []  # вся информация о сгенерированных слайдах

    def add_slide(self, page_name: str, title: str, icons: List[str]):
        self.used_titles.add(title.lower().strip())
        for icon in icons:
            self.used_icons.add(icon.lower().strip())
        self.slide_history.append({
            "page_name": page_name,
            "title": title,
            "icons": icons
        })

    def get_context_for_next_slide(self) -> str:
        """Генерирует строку контекста для следующего слайда."""
        context_parts = []
        if self.used_titles:
            context_parts.append(f"Уже использованные заголовки: {', '.join(sorted(self.used_titles))}")
        if self.used_icons:
            context_parts.append(f"Уже использованные иконки: {', '.join(sorted(self.used_icons))}")
        if self.slide_history:
            last_slides = self.slide_history[-3:]  # последние 3 слайда
            prev = "\n".join(f"  - {s['page_name']}: {s['title']}" for s in last_slides)
            context_parts.append(f"Предыдущие слайды:\n{prev}")
        return "\n".join(context_parts)