from pathlib import Path
from typing import List, Dict, Optional
from icon_manager import IconLibrary

class IconTool:
    def __init__(self, icons_dir: Path):
        self.lib = IconLibrary(icons_dir)

    def search(self, query: str, style: Optional[str] = None, flat: Optional[bool] = None) -> List[Dict]:
        variants = self.lib.search(query, style=style, flat=flat)
        return [{"name": v.name, "style": v.style, "flat": v.is_flat} for v in variants[:15]]

    def get_best_match(self, description: str) -> Optional[str]:
        """По описанию находит наиболее подходящую иконку."""
        # Простейшая эвристика: ищем по ключевым словам
        keywords = description.lower().split()
        for kw in keywords:
            matches = self.lib.search(kw, style='regular')
            if matches:
                return matches[0].name
        # fallback
        all_icons = self.lib.search("")
        if all_icons:
            return all_icons[0].name
        return None