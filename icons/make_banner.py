"""Generate a wide project banner (banner.png) + branded Inno Setup wizard images
from the DevCat Split icon. Matches the app's dark theme + Joy-Con neon colours."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from make_cat_icons import variant_split_cat  # noqa: E402

NEON_RED = (255, 69, 84)
NEON_BLUE = (0, 195, 227)
WHITE = (245, 246, 248)
MUTED = (154, 160, 166)

FONTS = "C:/Windows/Fonts/"
def font(name, size):
    return ImageFont.truetype(FONTS + name, size)


def vgradient(size, top, bottom):
    w, h = size
    g = Image.new("RGB", (1, h))
    px = g.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
    return g.resize((w, h))


def diag(size, c1, c2):
    s = 64
    g = Image.new("RGB", (s, s)); p = g.load()
    for y in range(s):
        for x in range(s):
            t = (x + y) / (2 * (s - 1))
            p[x, y] = tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3))
    return g.resize(size, Image.BICUBIC)


def make_banner():
    """Wide banner for the README / GitHub (1200x360)."""
    W, H = 1200, 360
    img = diag((W, H), (30, 32, 38), (12, 14, 21)).convert("RGBA")
    d = ImageDraw.Draw(img)

    # Subtle Joy-Con glow accents in the corners.
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([-160, -220, 220, 160], fill=NEON_RED + (46,))
    gd.ellipse([W - 240, H - 200, W + 160, H + 200], fill=NEON_BLUE + (46,))
    img = Image.alpha_composite(img, glow.filter(__import__("PIL.ImageFilter", fromlist=["GaussianBlur"]).GaussianBlur(60)))
    d = ImageDraw.Draw(img)

    # Cat icon on the left.
    cat = variant_split_cat().resize((260, 260), Image.LANCZOS)
    img.alpha_composite(cat, (56, (H - 260) // 2))

    # Title (two lines) + neon "&".
    x = 360
    f_title = font("segoeuib.ttf", 76)
    d.text((x, 96), "Switch Cheats Scraper", font=f_title, fill=WHITE)
    y2 = 96 + 84
    amp = "& "
    d.text((x, y2), amp, font=f_title, fill=NEON_BLUE)
    aw = d.textlength(amp, font=f_title)
    d.text((x + aw, y2), "Downloader", font=f_title, fill=WHITE)

    # Joy-Con accent divider.
    dy = y2 + 92
    d.rounded_rectangle([x, dy, x + 150, dy + 7], radius=3, fill=NEON_RED)
    d.rounded_rectangle([x + 158, dy, x + 300, dy + 7], radius=3, fill=NEON_BLUE)

    # Tagline.
    f_sub = font("seguisb.ttf", 27)
    d.text((x, dy + 22), "Scrape · manage · export Nintendo Switch cheats",
           font=f_sub, fill=MUTED)

    out = ROOT / "banner.png"
    img.convert("RGB").save(out)
    print("wrote", out, img.size)


def _flatten(img, bg):
    base = Image.new("RGB", img.size, bg)
    base.paste(img, (0, 0), img)
    return base


def make_wizard():
    """Inno Setup wizard images, branded with the cat + app name."""
    master = variant_split_cat()
    NAVY = (16, 20, 32)

    # Large left banner 164x314: cat on top, wrapped app name below, neon divider.
    big = vgradient((164, 314), (26, 32, 48), (12, 15, 24)).convert("RGBA")
    d = ImageDraw.Draw(big)
    big.alpha_composite(master.resize((96, 96), Image.LANCZOS), (34, 26))
    d.rounded_rectangle([34, 138, 74, 143], radius=2, fill=NEON_RED)
    d.rounded_rectangle([78, 138, 118, 143], radius=2, fill=NEON_BLUE)
    f = font("segoeuib.ttf", 15)
    fs = font("segoeui.ttf", 10)
    for i, line in enumerate(("Switch", "Cheats", "Scraper &", "Downloader")):
        d.text((34, 158 + i * 21), line, font=f, fill=WHITE)
    d.text((34, 250), "by DevCatSKZ", font=fs, fill=MUTED)
    _flatten(big, NAVY).save(ROOT / "wizard_large.bmp", format="BMP")
    print("wrote wizard_large.bmp")

    # Small top-right 55x58 (white bg, just the icon).
    small = Image.new("RGBA", (55, 58), (255, 255, 255, 255))
    small.alpha_composite(master.resize((50, 50), Image.LANCZOS), (2, 4))
    _flatten(small, (255, 255, 255)).save(ROOT / "wizard_small.bmp", format="BMP")
    print("wrote wizard_small.bmp")


if __name__ == "__main__":
    make_banner()
    make_wizard()
    print("done")
