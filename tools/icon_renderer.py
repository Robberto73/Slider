"""
Инструмент рендеринга иконок Phosphor в PNG с прозрачностью.
Работает на Pillow. Использует готовые PNG из папки PNGs и перекрашивает их.
Не требует Cairo или cairosvg.
"""

import tempfile
from pathlib import Path
from typing import Optional
from io import BytesIO
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from icon_manager import IconLibrary


class IconRenderer:
    def __init__(self, icons_base_dir: Path):
        self.lib = IconLibrary(icons_base_dir)
        self.png_dir = icons_base_dir / "PNGs" if icons_base_dir else None
        self.cache = {}

    def render(
        self,
        icon_name: str,
        size: int = 200,
        fill_color: str = "#000000",
        style: str = "regular",
        decorative_shape: Optional[str] = None,
        shape_color: Optional[str] = None,
        output_dir: Optional[Path] = None,
    ) -> Path:
        cache_key = (icon_name, size, fill_color, style, decorative_shape, shape_color)
        if cache_key in self.cache:
            cached_path = self.cache[cache_key]
            if cached_path.exists():
                return cached_path

        # Пытаемся найти готовый PNG
        png_img = None
        if self.png_dir and self.png_dir.exists():
            # ищем точное совпадение имени с расширением .png
            png_path = self.png_dir / f"{icon_name}.png"
            if not png_path.exists():
                # попробуем в подпапках стилей, как в SVGs
                for sub in ["regular", "bold", "thin", "light", "fill", "duotone"]:
                    candidate = self.png_dir / sub / f"{icon_name}.png"
                    if candidate.exists():
                        png_path = candidate
                        break
            if png_path.exists():
                png_img = Image.open(png_path).convert("RGBA")

        if png_img is not None:
            # Перекрашиваем: заменяем цвет заливки (чёрный по умолчанию) на fill_color
            png_img = self._recolor_png(png_img, fill_color)
            # Изменяем размер
            png_img = png_img.resize((size, size), Image.LANCZOS)
        else:
            # Fallback: создаём изображение с буквами
            png_img = self._create_fallback_image(icon_name, size, fill_color)

        # Добавляем декоративную подложку, если нужно
        if decorative_shape and shape_color:
            png_img = self._add_decorative_shape(png_img, decorative_shape, shape_color)

        # Сохраняем
        if output_dir is None:
            output_dir = Path(tempfile.gettempdir()) / "kimi_rendered_icons"
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{icon_name}_{style}_{fill_color.replace('#', '')}"
        if decorative_shape:
            safe_name += f"_{decorative_shape}_{shape_color.replace('#', '')}"
        output_path = output_dir / f"{safe_name}.png"
        png_img.save(output_path, format="PNG")

        self.cache[cache_key] = output_path
        return output_path

    def _recolor_png(self, img: Image.Image, target_color: str) -> Image.Image:
        """Заменяет непрозрачные пиксели на target_color с сохранением яркости/прозрачности."""
        # Преобразуем цвет
        r, g, b = self._hex_to_rgb(target_color)
        # Перебираем пиксели (можно оптимизировать, но для 200px норм)
        pixels = img.load()
        for y in range(img.height):
            for x in range(img.width):
                pr, pg, pb, pa = pixels[x, y]
                if pa > 0:
                    # Сохраняем альфа-канал, заменяем цвет
                    pixels[x, y] = (r, g, b, pa)
        return img

    def _create_fallback_image(self, icon_name: str, size: int, fill_color: str) -> Image.Image:
        """Создаёт круг с первыми буквами названия."""
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Круг цвета fill_color
        draw.ellipse([4, 4, size-4, size-4], fill=fill_color)
        # Белый текст
        text = icon_name[:2].upper()
        try:
            font = ImageFont.truetype("arial.ttf", size // 2)
        except:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        draw.text(((size-tw)/2, (size-th)/2), text, fill="white", font=font)
        return img

    def _add_decorative_shape(self, icon_img: Image.Image, shape: str, color: str) -> Image.Image:
        """Добавляет подложку."""
        size = icon_img.size[0]
        shape_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(shape_img)
        margin = int(size * 0.05)
        if shape == "circle":
            draw.ellipse([margin, margin, size-margin, size-margin], fill=color)
        elif shape == "square":
            draw.rectangle([margin, margin, size-margin, size-margin], fill=color)
        return Image.alpha_composite(shape_img, icon_img)

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple:
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))