"""README banner built around the new app logo (Joy-Con split + download).
Dark, calm backdrops so the colourful logo pops. 3 variants; renders at 2x."""
import sys
import os
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from applogo import app_logo  # noqa: E402

NEON_RED = (255, 69, 84)
NEON_BLUE = (0, 195, 227)
VIOLET = (120, 92, 230)
WHITE = (246, 247, 249)
MUTED = (156, 164, 176)
FAINT = (108, 116, 130)
FONTS = "C:/Windows/Fonts/"
SCALE = 2


def font(name, size):
    return ImageFont.truetype(FONTS + name, int(size * SCALE))


def S(v):
    return int(round(v * SCALE))


def diag(size, c1, c2):
    s = 64
    g = Image.new("RGB", (s, s)); p = g.load()
    for y in range(s):
        for x in range(s):
            t = (x + y) / (2 * (s - 1))
            p[x, y] = tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3))
    return g.resize(size, Image.BICUBIC)


def glow(size, center, radius, color, alpha):
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    cx, cy = center
    ImageDraw.Draw(layer).ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                                  fill=color + (alpha,))
    return layer.filter(ImageFilter.GaussianBlur(radius * 0.5))


def over(a, b):
    return Image.alpha_composite(a, b)


def vignette(size, strength=130):
    W, H = size
    v = Image.new("L", size, 0)
    ImageDraw.Draw(v).ellipse([-W * 0.12, -H * 0.3, W * 1.12, H * 1.3], fill=255)
    v = v.filter(ImageFilter.GaussianBlur(S(80)))
    dark = Image.new("RGBA", size, (0, 0, 0, 0))
    dark.putalpha(Image.eval(v, lambda p: strength - int(p * strength / 255)))
    return dark


def dot_grid(size, spacing, alpha, r):
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for y in range(0, size[1], spacing):
        for x in range(0, size[0], spacing):
            d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, alpha))
    return layer


def bg_aurora(size):
    img = diag(size, (22, 25, 36), (9, 10, 16)).convert("RGBA")
    img = over(img, glow(size, (S(1120), S(300)), S(360), NEON_BLUE, 55))
    img = over(img, glow(size, (S(700), S(520)), S(340), VIOLET, 40))
    img = over(img, glow(size, (S(300), S(120)), S(260), NEON_RED, 34))
    img = over(img, dot_grid(size, S(34), 7, S(1)))
    img = over(img, vignette(size, 130))
    return img


def bg_code(size):
    img = diag(size, (20, 23, 33), (9, 10, 16)).convert("RGBA")
    img = over(img, glow(size, (S(1120), S(310)), S(340), NEON_BLUE, 45))
    img = over(img, glow(size, (S(320), S(140)), S(260), NEON_RED, 30))
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    mono = font("consola.ttf", 13)
    random.seed(5)
    for row in range(15):
        y = S(18) + row * S(22)
        for col in range(11):
            x = S(26) + col * S(150)
            a = max(4, 18 - col * 2)
            ld.text((x, y), "".join(random.choice("0123456789ABCDEF") for _ in range(8)),
                    font=mono, fill=(NEON_BLUE if (row + col) % 2 else NEON_RED) + (a,))
    img = over(img, layer)
    img = over(img, vignette(size, 120))
    return img


def bg_minimal(size):
    W, H = size
    img = diag(size, (24, 27, 38), (11, 12, 19)).convert("RGBA")
    img = over(img, glow(size, (S(1050), S(340)), S(300), NEON_BLUE, 30))
    img = over(img, vignette(size, 150))
    return img


BACKGROUNDS = {"aurora": bg_aurora, "code": bg_code, "minimal": bg_minimal}


def foreground(img):
    W, H = img.size
    # logo left
    img.alpha_composite(app_logo().resize((S(252), S(252)), Image.LANCZOS), (S(46), S(182) - S(126)))
    d = ImageDraw.Draw(img)
    x = S(336)
    f_title = font("segoeuib.ttf", 66)
    d.text((x, S(84)), "Switch Cheats Scraper", font=f_title, fill=WHITE)
    y2 = S(84) + S(78)
    d.text((x, y2), "&", font=f_title, fill=NEON_BLUE)
    aw = d.textlength("&  ", font=f_title)
    d.text((x + aw, y2), "Downloader", font=f_title, fill=WHITE)
    # accent bar
    g = Image.new("RGB", (S(320), 1)); pp = g.load()
    for i in range(S(320)):
        t = i / (S(320) - 1)
        pp[i, 0] = tuple(int(NEON_RED[j] * (1 - t) + NEON_BLUE[j] * t) for j in range(3))
    bar = g.resize((S(320), S(6)))
    bm = Image.new("L", bar.size, 0)
    ImageDraw.Draw(bm).rounded_rectangle([0, 0, bar.size[0] - 1, bar.size[1] - 1], radius=S(3), fill=255)
    img.paste(bar, (x + S(2), y2 + S(82)), bm)
    d.text((x, y2 + S(100)), "Nintendo Switch cheat codes — all sources, one database",
           font=font("seguisb.ttf", 22), fill=MUTED)
    d.text((x + S(2), y2 + S(134)),
           "S C R A P E     ·     D O W N L O A D     ·     M A N A G E     ·     E X P O R T   T O   S D",
           font=font("seguisb.ttf", 14), fill=FAINT)
    return img


def make(kind, out):
    size = (S(1200), S(360))
    img = foreground(BACKGROUNDS[kind](size))
    img.convert("RGB").save(out)
    print("wrote", kind, "->", out, img.size)


if __name__ == "__main__":
    outdir = os.environ.get("BANNER_OUTDIR", str(ROOT))
    for kind in ("aurora", "code", "minimal"):
        make(kind, os.path.join(outdir, f"bannerX_{kind}.png"))
