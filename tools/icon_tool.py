# tools/icon_tool.py
from pathlib import Path
from typing import List, Dict, Optional
from icon_manager import IconLibrary, IconSemantics

class IconTool:
    def __init__(self, icons_dir: Path):
        self.lib = IconLibrary(icons_dir)

    def search(self, query: str, style: Optional[str] = None, use_semantics: bool = True) -> List[Dict]:
        # Сначала семантический поиск
        if use_semantics:
            semantic_matches = IconSemantics.get_icons(query)
            if semantic_matches:
                # Для каждого имени ищем вариант с нужным стилем
                result_variants = []
                for name in semantic_matches:
                    variant = self.lib.get_best_variant(name, style) if style else self.lib.get_best_variant(name, 'regular')
                    if variant:
                        result_variants.append({"name": variant.name, "style": variant.style, "flat": variant.is_flat})
                if result_variants:
                    return result_variants[:10]

        # Обычный поиск по подстроке
        variants = self.lib.search(query, style=style)
        return [{"name": v.name, "style": v.style, "flat": v.is_flat} for v in variants[:15]]

    def get_best_match(self, description: str, preferred_style: str = 'regular') -> Optional[str]:
        """По описанию находит наиболее подходящую иконку, семантически или поиском."""
        # description может быть 'деньги' или 'щит, безопасность'
        # Извлекаем ключевое слово
        desc_lower = description.lower().strip()
        # Пробуем семантику
        semantic_matches = IconSemantics.get_icons(desc_lower)
        if semantic_matches:
            for name in semantic_matches:
                variant = self.lib.get_best_variant(name, preferred_style)
                if variant:
                    return variant.name

        # Обычный поиск
        variants = self.lib.search(desc_lower, style=preferred_style)
        if variants:
            return variants[0].name
        # Без стиля
        variants = self.lib.search(desc_lower)
        return variants[0].name if variants else None