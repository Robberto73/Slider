"""
Модуль управления библиотекой иконок Phosphor.
Поиск, выбор вариантов, кастомизация SVG (цвет, размер).
Готов к использованию в качестве инструмента для GigaChat-агента.
"""

import re
import tempfile
from pathlib import Path
from typing import List, Optional, Dict
from lxml import etree


class IconVariant:
    """Конкретный файл иконки с известным стилем."""
    def __init__(self, path: Path, style: str, is_flat: bool = False):
        self.path = path
        self.style = style          # bold, regular, light, thin, fill, duotone
        self.is_flat = is_flat      # True для "SVGs Flat", False для обычных "SVGs"
        self.name = path.stem

    def __repr__(self):
        return f"IconVariant({self.name}, style={self.style}, flat={self.is_flat})"


class IconLibrary:
    """
    Сканирует папку icons и строит индекс для быстрого поиска.
    """
    def __init__(self, icons_base_dir: Path):
        self.base_dir = Path(icons_base_dir)
        self._index: Dict[str, List[IconVariant]] = {}
        self._initialized = False

    def _initialize(self):
        if self._initialized:
            return
        if not self.base_dir.exists():
            raise FileNotFoundError(f"Директория иконок не найдена: {self.base_dir}")

        styles = ['bold', 'regular', 'light', 'thin', 'fill', 'duotone']

        # Обычные SVG (объёмные)
        svg_dir = self.base_dir / 'SVGs'
        if svg_dir.exists():
            for style in styles:
                style_dir = svg_dir / style
                if not style_dir.exists():
                    continue
                for svg_file in style_dir.glob("*.svg"):
                    name = svg_file.stem.lower()
                    variant = IconVariant(svg_file, style, is_flat=False)
                    self._index.setdefault(name, []).append(variant)

        # Плоские SVG
        flat_svg_dir = self.base_dir / 'SVGs Flat'
        if flat_svg_dir.exists():
            for style in styles:
                style_dir = flat_svg_dir / style
                if not style_dir.exists():
                    continue
                for svg_file in style_dir.glob("*.svg"):
                    name = svg_file.stem.lower()
                    variant = IconVariant(svg_file, style, is_flat=True)
                    self._index.setdefault(name, []).append(variant)

        # Плоские PNG (резерв)
        png_dir = self.base_dir / 'PNGs'
        if png_dir.exists():
            for png_file in png_dir.glob("*.png"):
                name = png_file.stem.lower()
                variant = IconVariant(png_file, style="regular", is_flat=True)
                self._index.setdefault(name, []).append(variant)

        self._initialized = True

    def search(self, query: str, style: Optional[str] = None, flat: Optional[bool] = None) -> List[IconVariant]:
        """
        Поиск иконок. `query` ищется как подстрока в имени файла.
        """
        self._initialize()
        result = []
        q = query.lower()
        for name, variants in self._index.items():
            if q in name:
                for v in variants:
                    if style and v.style != style:
                        continue
                    if flat is not None and v.is_flat != flat:
                        continue
                    result.append(v)
        return result

    def get_best_variant(self, name: str, style: str = 'regular', prefer_flat: bool = False) -> Optional[IconVariant]:
        """
        Возвращает наилучший вариант по точному имени и стилю.
        Если стиль не указан или не найден – пробует regular, затем любой.
        """
        variants = self.search(name, style=style, flat=prefer_flat)
        if not variants and style != 'regular':
            # Откат к regular
            variants = self.search(name, style='regular', flat=prefer_flat)
        if not variants:
            # Вообще любой стиль
            variants = self.search(name)
        return variants[0] if variants else None

    def customize_svg(self, svg_path: Path, fill_color: Optional[str] = None,
                      stroke_color: Optional[str] = None, size: Optional[int] = None) -> Path:
        """
        Создаёт временную копию SVG с изменёнными цветами и размером.
        Возвращает путь к новому файлу.
        """
        content = svg_path.read_text(encoding='utf-8')
        root = etree.fromstring(content.encode('utf-8'))

        if size:
            root.set('width', str(size))
            root.set('height', str(size))

        def apply_color(elem, attr, color):
            val = elem.get(attr)
            if val and val.lower() != 'none':
                elem.set(attr, color)

        if fill_color:
            for elem in root.iter():
                apply_color(elem, 'fill', fill_color)
        if stroke_color:
            for elem in root.iter():
                apply_color(elem, 'stroke', stroke_color)

        tmp_dir = Path(tempfile.gettempdir()) / 'kimi_icons_custom'
        tmp_dir.mkdir(exist_ok=True)
        out_name = svg_path.stem
        if fill_color:
            out_name += f"_{fill_color.replace('#', '')}"
        out_path = tmp_dir / f"{out_name}.svg"
        out_path.write_bytes(etree.tostring(root, pretty_print=True))
        return out_path

    def list_all_categories(self) -> Dict[str, List[str]]:
        """Возвращает словарь {стиль: [список_имён_иконок]}."""
        self._initialize()
        cats: Dict[str, List[str]] = {}
        for variants in self._index.values():
            for v in variants:
                cats.setdefault(v.style, []).append(v.name)
        return cats

class IconSemantics:
    _mapping = {
        "безопасность": ["shield", "shield-check", "lock-key", "fingerprint"],
        "рост": ["trend-up", "chart-line-up", "arrow-up", "rocket"],
        "инновации": ["atom", "cpu", "circuitry", "lightbulb-filament"],
        "команда": ["users", "handshake", "user-circle-gear", "person-arms-spread"],
        "деньги": ["currency-dollar", "bank", "wallet", "credit-card"],
        "время": ["clock", "hourglass", "calendar", "timer"],
        "связь": ["phone", "envelope", "chat-centered-text", "share-network"],
        "геолокация": ["map-pin", "globe-hemisphere-west", "navigation-arrow", "compass"],
    }

    @classmethod
    def get_icons(cls, keyword: str) -> list:
        """Возвращает список подходящих иконок по ключевому слову."""
        if keyword in cls._mapping:
            return cls._mapping[keyword]
        # ищем частичное совпадение по ключам
        for k, v in cls._mapping.items():
            if keyword in k or k in keyword:
                return v
        return []  # вернуть пустой, тогда модель использует общий поиск