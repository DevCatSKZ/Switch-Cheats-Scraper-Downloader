"""The official app logo: a bold diagonal Joy-Con split (Nintendo Switch red/blue)
with a big download arrow + faint cheat-code hex. app_logo() -> 1024 RGBA icon
(rounded square, transparent corners) — the single source of truth for the icon,
wizard images and the README banner."""
import random
from PIL import Image, ImageDraw, ImageFont, ImageFilter

S = 1024
R = int(S * 0.235)
WHITE = (247, 248, 250, 255)
FONTS = "C:/Windows/Fonts/"


def rmask(size, radius):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def _grad(size, c1, c2):
    s = 64
    g = Image.new("RGB", (s, s)); p = g.load()
    for y in range(s):
        for x in range(s):
            t = (x + y) / (2 * (s - 1))
            p[x, y] = tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3))
    return g.resize((size, size), Image.BICUBIC)


def _dl_arrow(d, cx, cy, r, color=WHITE):
    st = int(r * 0.30)
    d.rounded_rectangle([cx - st, cy - int(r * 0.78), cx + st, cy + int(r * 0.06)],
                        radius=int(st * 0.7), fill=color)
    d.polygon([(cx - int(r * 0.62), cy - int(r * 0.10)), (cx + int(r * 0.62), cy - int(r * 0.10)),
               (cx, cy + int(r * 0.58))], fill=color)
    d.rounded_rectangle([cx - int(r * 0.6), cy + int(r * 0.66), cx + int(r * 0.6), cy + int(r * 0.86)],
                        radius=int(r * 0.10), fill=color)


def _hex_lines(img, box, alpha, seed=2, cols=5, rows=10):
    d = ImageDraw.Draw(img)
    mono = ImageFont.truetype(FONTS + "consola.ttf", int(S * 0.03))
    random.seed(seed)
    x0, y0, x1, y1 = box
    step = (y1 - y0) / rows
    for r in range(rows):
        line = " ".join("".join(random.choice("0123456789ABCDEF") for _ in range(5)) for _ in range(cols))
        d.text((x0, y0 + r * step), line, font=mono, fill=(200, 220, 255, alpha))


def app_logo(hex_alpha=16, sheen=True):
    """Bold diagonal red|blue split + download arrow. Full rounded-square icon."""
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    m = rmask(S, R)
    left = _grad(S, (232, 62, 82), (150, 30, 48)).convert("RGBA")
    right = _grad(S, (0, 158, 192), (0, 104, 142)).convert("RGBA")
    tri = Image.new("L", (S, S), 0)
    ImageDraw.Draw(tri).polygon([(0, 0), (S, 0), (0, S)], fill=255)
    img.paste(Image.composite(left, right, tri), (0, 0), m)
    # soft diagonal seam
    seam = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(seam).line([(S, 0), (0, S)], fill=(255, 255, 255, 55), width=int(S * 0.012))
    img = Image.alpha_composite(img, Image.composite(
        seam.filter(ImageFilter.GaussianBlur(int(S * 0.01))),
        Image.new("RGBA", (S, S), (0, 0, 0, 0)), m))
    if sheen:
        sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([0, 0, S - 1, int(S * 0.5)], radius=R, fill=(255, 255, 255, 14))
        img = Image.alpha_composite(img, Image.composite(sh, Image.new("RGBA", (S, S), (0, 0, 0, 0)), m))
    if hex_alpha:
        _hex_lines(img, [int(S * 0.09), int(S * 0.1), int(S * 0.9), int(S * 0.9)], hex_alpha)
    d = ImageDraw.Draw(img)
    _dl_arrow(d, S // 2, int(S * 0.5), int(S * 0.32), color=WHITE)
    return img


if __name__ == "__main__":
    from pathlib import Path
    out = Path(__file__).resolve().parent / "applogo_preview.png"
    app_logo().save(out)
    print("wrote", out)
