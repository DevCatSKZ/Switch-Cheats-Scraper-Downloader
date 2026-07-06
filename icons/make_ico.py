"""Build app.ico (multi-resolution) + app_icon.png + Inno Setup wizard images
from the official app logo (Joy-Con split + download)."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from applogo import app_logo  # noqa: E402

master = app_logo()  # 1024x1024 RGBA, rounded, transparent corners

# --- app.ico (Windows multi-resolution) ---
ICO = HERE.parent / "app.ico"
sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]
master.resize((256, 256), Image.LANCZOS).save(ICO, format="ICO", sizes=sizes)
print("wrote", ICO)

# also a PNG copy next to the code for the Tk window icon fallback
master.resize((256, 256), Image.LANCZOS).save(HERE.parent / "app_icon.png")
print("wrote app_icon.png")


# --- Inno Setup wizard images (BMP, no alpha) ---
def flatten(img, bg):
    base = Image.new("RGB", img.size, bg)
    base.paste(img, (0, 0), img)
    return base


NAVY = (14, 16, 24)

# Large left banner (Welcome/Finished). 164x314.
big = Image.new("RGBA", (164, 314), NAVY + (255,))
grad_top, grad_bot = (24, 28, 44), (11, 13, 21)
for y in range(314):
    t = y / 313
    c = tuple(int(grad_top[i] * (1 - t) + grad_bot[i] * t) for i in range(3))
    ImageDraw.Draw(big).line([(0, y), (164, y)], fill=c + (255,))
big.alpha_composite(master.resize((120, 120), Image.LANCZOS), (22, 40))
flatten(big, NAVY).save(HERE.parent / "wizard_large.bmp", format="BMP")
print("wrote wizard_large.bmp")

# Small top-right image (other pages). 55x58.
small = Image.new("RGBA", (55, 58), (255, 255, 255, 255))
small.alpha_composite(master.resize((50, 50), Image.LANCZOS), (2, 4))
flatten(small, (255, 255, 255)).save(HERE.parent / "wizard_small.bmp", format="BMP")
print("wrote wizard_small.bmp")
print("done")
