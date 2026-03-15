from __future__ import annotations

from typing import Any

from .config import ButtonSpec, PageSpec
from .dependencies import ImageDraw, ImageFont, PILHelper, PIL_AVAILABLE


def darken(color: tuple[int, int, int], factor: float = 0.45) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(channel * factor))) for channel in color)


def render_solid_bmp(deck: Any, color: tuple[int, int, int]) -> bytes:
    blank_image = bytes(getattr(deck, "BLANK_KEY_IMAGE", b""))
    if len(blank_image) < 54:
        raise RuntimeError("This example expects a Stream Deck Mini-style visual deck.")

    blue, green, red = color[2], color[1], color[0]
    payload = bytearray(blank_image)
    for offset in range(54, len(payload), 3):
        payload[offset:offset + 3] = bytes((blue, green, red))
    return bytes(payload)


def text_position(draw: Any, label: str, font: Any, width: int, height: int) -> tuple[float, float]:
    if hasattr(draw, "textbbox"):
        left, top, right, bottom = draw.textbbox((0, 0), label, font=font)
        text_width = right - left
        text_height = bottom - top
    else:
        text_width, text_height = draw.textsize(label, font=font)

    return (width - text_width) / 2, (height - text_height) / 2


def render_key_image(deck: Any, spec: ButtonSpec, pressed: bool) -> bytes:
    fill = darken(spec.color) if pressed else spec.color

    if spec.action == "noop" and not spec.label:
        return render_solid_bmp(deck, fill)

    if PIL_AVAILABLE:
        image = PILHelper.create_key_image(deck, background="black")
        draw = ImageDraw.Draw(image)
        width, height = image.size
        draw.rounded_rectangle(
            (4, 4, width - 5, height - 5),
            radius=12,
            fill=fill,
            outline=(255, 255, 255),
            width=2 if pressed else 1,
        )

        font = ImageFont.load_default()
        x_pos, y_pos = text_position(draw, spec.label, font, width, height)
        draw.text((x_pos, y_pos), spec.label, font=font, fill=(255, 255, 255))
        return PILHelper.to_native_key_format(deck, image)

    return render_solid_bmp(deck, fill)


def update_key(deck: Any, key: int, spec: ButtonSpec, pressed: bool = False) -> None:
    image = render_key_image(deck, spec, pressed)
    with deck:
        deck.set_key_image(key, image)


def redraw_all_keys(deck: Any, page: PageSpec) -> None:
    with deck:
        for key, spec in enumerate(page.buttons):
            deck.set_key_image(key, render_key_image(deck, spec, pressed=False))


def print_help(page: PageSpec) -> None:
    print(f"Page: {page.title}")
    print("Key map:")
    for key, spec in enumerate(page.buttons):
        if spec.action == "noop" and not spec.label:
            continue

        print(f"  [{key}] {spec.description}")

    print("Press Ctrl+C to stop.")

    if not PIL_AVAILABLE:
        print("Pillow is not installed, so the keys use solid colors without text labels.")
        print("Install it with: pip install pillow")
