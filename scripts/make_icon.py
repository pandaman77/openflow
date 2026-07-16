"""Generate the OpenFlow app icon: a mic over a soundwave on a dark squircle,
in the app's amber-on-ink palette. Renders at 4x and downsamples for clean AA.
Outputs icon.png (512) and a multi-size icon.ico."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "apps" / "desktop" / "src-tauri" / "icons"

INK = (11, 20, 22)         # #0b1416 background
INK2 = (22, 36, 40)        # #162428 squircle top
AMBER = (242, 163, 92)     # #f2a35c
AMBER_HI = (247, 190, 130)
TEXT = (233, 239, 236)

S = 512
SS = 4  # supersample


def squircle_mask(size: int, radius_ratio: float = 0.42) -> Image.Image:
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    r = int(size * radius_ratio)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=255)
    return m


def vgrad(size: int, top: tuple, bottom: tuple) -> Image.Image:
    g = Image.new("RGB", (size, size), top)
    px = g.load()
    for y in range(size):
        t = y / size
        px_row = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(size):
            px[x, y] = px_row
    return g


def draw_icon() -> Image.Image:
    big = S * SS
    img = vgrad(big, INK2, INK).convert("RGBA")
    d = ImageDraw.Draw(img)
    cx = big // 2

    # --- microphone capsule ---
    mic_w = int(big * 0.20)
    mic_top = int(big * 0.20)
    mic_bot = int(big * 0.52)
    d.rounded_rectangle(
        [cx - mic_w // 2, mic_top, cx + mic_w // 2, mic_bot],
        radius=mic_w // 2, fill=AMBER,
    )
    # capsule highlight
    d.rounded_rectangle(
        [cx - mic_w // 2, mic_top, cx + mic_w // 2, mic_top + mic_w],
        radius=mic_w // 2, fill=AMBER_HI,
    )

    # --- mic arc (the U-shaped bracket) + stem ---
    arc_w = int(big * 0.34)
    arc_top = int(big * 0.34)
    arc_bot = int(big * 0.60)
    lw = int(big * 0.035)
    d.arc([cx - arc_w // 2, arc_top, cx + arc_w // 2, arc_bot],
          start=0, end=180, fill=TEXT, width=lw)
    stem_top = arc_bot - lw // 2
    stem_bot = int(big * 0.66)
    d.line([cx, stem_top, cx, stem_bot], fill=TEXT, width=lw)
    d.line([cx - int(big * 0.06), stem_bot, cx + int(big * 0.06), stem_bot],
           fill=TEXT, width=lw)

    # --- soundwave along the bottom ---
    wave_y = int(big * 0.78)
    amp = int(big * 0.055)
    wlw = int(big * 0.028)
    left = int(big * 0.20)
    right = int(big * 0.80)
    step = 2
    pts = []
    span = right - left
    for x in range(left, right + 1, step):
        t = (x - left) / span
        env = math.sin(t * math.pi)  # fade at the ends
        y = wave_y - int(math.sin(t * math.pi * 5) * amp * env)
        pts.append((x, y))
    d.line(pts, fill=AMBER, width=wlw, joint="curve")

    # downsample + squircle clip
    img = img.resize((S, S), Image.LANCZOS)
    mask = squircle_mask(S)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    icon = draw_icon()
    icon.save(OUT / "icon.png")
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icon.save(OUT / "icon.ico", sizes=sizes)
    print("wrote", OUT / "icon.png", "and icon.ico")


if __name__ == "__main__":
    main()
