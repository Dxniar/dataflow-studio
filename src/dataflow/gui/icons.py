"""Consistent small line icons drawn natively for the desktop UI."""

from functools import lru_cache

import customtkinter as ctk
from PIL import Image, ImageDraw


@lru_cache(maxsize=96)
def icon(name: str, color: str = "#92A0B2", size: int = 18) -> ctk.CTkImage:
    scale = 4
    image = Image.new("RGBA", (24 * scale, 24 * scale))
    draw = ImageDraw.Draw(image)

    def line(points, width=1.6):
        draw.line(
            [(int(x * scale), int(y * scale)) for x, y in points],
            fill=color,
            width=round(width * scale),
            joint="curve",
        )

    def rect(box, radius=2):
        draw.rounded_rectangle(
            tuple(int(v * scale) for v in box),
            radius=radius * scale,
            outline=color,
            width=round(1.6 * scale),
        )

    if name in {"table", "brand"}:
        rect((3, 4, 21, 20))
        line([(3, 9), (21, 9)])
        line([(9, 9), (9, 20)])
        line([(3, 14.5), (21, 14.5)])
    elif name == "folder":
        line([(3, 7), (3, 5), (9, 5), (11, 8), (21, 8), (21, 20), (3, 20), (3, 7)])
    elif name == "file":
        line([(6, 3), (14, 3), (19, 8), (19, 21), (5, 21), (5, 3), (6, 3)])
        line([(14, 3), (14, 8), (19, 8)])
        line([(8, 12), (16, 12)])
        line([(8, 16), (14, 16)])
    elif name == "clean":
        line([(15, 3), (8, 14), (16, 19), (20, 11), (15, 8)])
        line([(8, 14), (4, 17), (4, 20), (13, 21), (16, 19)])
        line([(7, 17), (10, 20)])
    elif name == "transform":
        line([(3, 7), (20, 7), (16, 3)])
        line([(3, 17), (20, 17)])
        line([(7, 13), (3, 17), (7, 21)])
    elif name == "merge":
        line([(4, 4), (4, 8), (12, 13), (12, 21)])
        line([(20, 4), (20, 8), (12, 13)])
        line([(8, 17), (12, 21), (16, 17)])
    elif name == "convert":
        line([(4, 8), (4, 5), (20, 5), (20, 8)])
        line([(4, 16), (4, 19), (20, 19), (20, 16)])
        line([(8, 12), (16, 12), (13, 9)])
        line([(16, 12), (13, 15)])
    elif name == "compare":
        rect((3, 4, 21, 20))
        line([(12, 4), (12, 20)])
        line([(6, 9), (9, 9)])
        line([(15, 15), (18, 15)])
    elif name == "history":
        draw.arc(
            (3 * scale, 3 * scale, 21 * scale, 21 * scale),
            215,
            550,
            fill=color,
            width=round(1.6 * scale),
        )
        line([(3, 4), (3, 9), (8, 9)])
        line([(12, 7), (12, 12), (16, 14)])
    elif name == "settings":
        for y, x in [(5, 9), (12, 16), (19, 7)]:
            line([(3, y), (21, y)])
            draw.ellipse(
                ((x - 2) * scale, (y - 2) * scale, (x + 2) * scale, (y + 2) * scale),
                fill="#10161F",
                outline=color,
                width=round(1.6 * scale),
            )
    elif name in {"upload", "download"}:
        line([(4, 15), (4, 20), (20, 20), (20, 15)])
        line([(12, 16), (12, 3)])
        if name == "upload":
            line([(7, 8), (12, 3), (17, 8)])
        else:
            line([(7, 11), (12, 16), (17, 11)])
    elif name == "play":
        line([(8, 4), (20, 12), (8, 20), (8, 4)])
    elif name == "check":
        line([(4, 12), (9, 17), (20, 6)], 2)
    elif name == "arrow_right":
        line([(4, 12), (20, 12), (14, 6)])
        line([(20, 12), (14, 18)])
    elif name in {"close", "trash"}:
        line([(7, 7), (17, 17)])
        line([(17, 7), (7, 17)])
    elif name == "chevron_down":
        line([(6, 9), (12, 15), (18, 9)])
    image = image.resize((size * 2, size * 2), Image.Resampling.LANCZOS)
    return ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))
