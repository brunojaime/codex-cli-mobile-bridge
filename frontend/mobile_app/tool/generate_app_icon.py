from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image, ImageChops, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
BRANDING_DIR = ROOT / "assets" / "branding"
ICON_SIZE = 1024


def _lerp(start: int, end: int, alpha: float) -> int:
    return round(start + (end - start) * alpha)


def _blend(start: tuple[int, int, int], end: tuple[int, int, int], alpha: float):
    return tuple(_lerp(left, right, alpha) for left, right in zip(start, end))


def _vertical_gradient(
    size: int,
    top: tuple[int, int, int],
    bottom: tuple[int, int, int],
) -> Image.Image:
    image = Image.new("RGBA", (size, size))
    pixels = image.load()
    for y in range(size):
        color = _blend(top, bottom, y / (size - 1))
        for x in range(size):
            pixels[x, y] = (*color, 255)
    return image


def _radial_glow(
    size: int,
    center: tuple[float, float],
    radius: float,
    color: tuple[int, int, int],
    strength: float,
) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pixels = image.load()
    cx, cy = center
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            distance = (dx * dx + dy * dy) ** 0.5
            if distance >= radius:
                continue
            alpha = (1.0 - (distance / radius)) ** 2.2
            pixels[x, y] = (*color, round(255 * alpha * strength))
    return image.filter(ImageFilter.GaussianBlur(radius=36))


def _rounded_rect_mask(
    size: int,
    padding: int,
    radius: int,
) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle(
        (padding, padding, size - padding, size - padding),
        radius=radius,
        fill=255,
    )
    return mask


def _draw_prompt_symbol(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    chevron_color: tuple[int, int, int, int],
    underscore_color: tuple[int, int, int, int],
) -> None:
    left, top, right, bottom = box
    width = right - left
    height = bottom - top
    stroke = round(width * 0.08)

    chevron_points = [
        (left + width * 0.18, top + height * 0.18),
        (left + width * 0.42, top + height * 0.5),
        (left + width * 0.18, top + height * 0.82),
    ]
    draw.line(chevron_points, fill=chevron_color, width=stroke, joint="curve")

    underscore_width = round(width * 0.26)
    underscore_height = round(height * 0.1)
    underscore_left = round(left + width * 0.52)
    underscore_top = round(top + height * 0.67)
    draw.rounded_rectangle(
        (
            underscore_left,
            underscore_top,
            underscore_left + underscore_width,
            underscore_top + underscore_height,
        ),
        radius=underscore_height // 2,
        fill=underscore_color,
    )


def _draw_bubble(
    image: Image.Image,
    *,
    bubble_fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int] | None = None,
    include_shadow: bool = True,
) -> None:
    draw = ImageDraw.Draw(image)
    bubble_box = (222, 234, 802, 726)
    bubble_radius = 168

    if include_shadow:
        shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle(
            bubble_box,
            radius=bubble_radius,
            fill=(0, 0, 0, 150),
        )
        shadow_draw.polygon(
            [(446, 726), (544, 726), (476, 820)],
            fill=(0, 0, 0, 150),
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=34))
        image.alpha_composite(shadow)

    draw.rounded_rectangle(bubble_box, radius=bubble_radius, fill=bubble_fill)
    draw.polygon(
        [(446, 726), (544, 726), (476, 820)],
        fill=bubble_fill,
    )

    if outline is not None:
        outline_width = 10
        draw.rounded_rectangle(
            bubble_box,
            radius=bubble_radius,
            outline=outline,
            width=outline_width,
        )
        draw.line(
            [(446, 726), (476, 820), (544, 726)],
            fill=outline,
            width=outline_width,
            joint="curve",
        )

    _draw_prompt_symbol(
        draw,
        (316, 358, 700, 636),
        chevron_color=(85, 214, 190, 255),
        underscore_color=(255, 200, 87, 255),
    )


def _create_full_icon() -> Image.Image:
    icon = _vertical_gradient(
        ICON_SIZE,
        top=(11, 18, 35),
        bottom=(21, 40, 68),
    )
    icon.alpha_composite(
        _radial_glow(
            ICON_SIZE,
            center=(760, 210),
            radius=390,
            color=(72, 215, 191),
            strength=0.55,
        )
    )
    icon.alpha_composite(
        _radial_glow(
            ICON_SIZE,
            center=(250, 820),
            radius=420,
            color=(255, 200, 87),
            strength=0.34,
        )
    )

    vignette = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    vignette_draw = ImageDraw.Draw(vignette)
    vignette_draw.rounded_rectangle(
        (28, 28, ICON_SIZE - 28, ICON_SIZE - 28),
        radius=220,
        outline=(255, 255, 255, 30),
        width=4,
    )
    icon.alpha_composite(vignette)

    _draw_bubble(
        icon,
        bubble_fill=(242, 247, 252, 255),
        outline=(255, 255, 255, 62),
        include_shadow=True,
    )

    soft_glare = _radial_glow(
        ICON_SIZE,
        center=(350, 240),
        radius=220,
        color=(255, 255, 255),
        strength=0.16,
    )
    icon.alpha_composite(soft_glare)

    mask = _rounded_rect_mask(ICON_SIZE, padding=0, radius=230)
    rounded = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    rounded.paste(icon, mask=mask)
    return rounded


def _create_foreground_icon() -> Image.Image:
    foreground = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    _draw_bubble(
        foreground,
        bubble_fill=(243, 248, 252, 255),
        outline=None,
        include_shadow=False,
    )

    halo = _radial_glow(
        ICON_SIZE,
        center=(512, 512),
        radius=330,
        color=(85, 214, 190),
        strength=0.14,
    )
    foreground = ImageChops.screen(foreground, halo)
    return foreground


def _save_images(images: Iterable[tuple[str, Image.Image]]) -> None:
    BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    for name, image in images:
        image.save(BRANDING_DIR / name)


def main() -> None:
    _save_images(
        (
            ("app_icon.png", _create_full_icon()),
            ("app_icon_ios.png", _create_full_icon()),
            ("app_icon_foreground.png", _create_foreground_icon()),
        )
    )


if __name__ == "__main__":
    main()
