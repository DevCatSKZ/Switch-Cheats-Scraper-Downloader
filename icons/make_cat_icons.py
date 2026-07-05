"""Cat-themed app icons (DevCat) in Nintendo-Switch Joy-Con neon colors."""
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent
S = 1024
R = int(S * 0.235)
NEON_RED = (255, 69, 84)
NEON_BLUE = (0, 195, 227)
WHITE = (255, 255, 255, 255)
INK = (28, 33, 46, 255)


def diagonal_gradient(size, c1, c2):
    small = 64
    g = Image.new("RGB", (small, small)); p = g.load()
    for y in range(small):
        for x in range(small):
            t = (x + y) / (2*(small-1))
            p[x, y] = tuple(int(c1[i]*(1-t)+c2[i]*t) for i in range(3))
    return g.resize((size, size), Image.BICUBIC)


def rmask(size, radius):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size-1, size-1], radius=radius, fill=255)
    return m


def canvas(c1, c2, sheen=True):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(diagonal_gradient(S, c1, c2), (0, 0), rmask(S, R))
    if sheen:
        sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([0, 0, S-1, int(S*0.5)], radius=R,
                                             fill=(255, 255, 255, 22))
        img = Image.alpha_composite(img, Image.composite(
            sh, Image.new("RGBA", (S, S), (0, 0, 0, 0)), rmask(S, R)))
    return img


def download_badge(img, cx, cy, r, ring=(34, 197, 94, 255)):
    d = ImageDraw.Draw(img)
    d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=ring)
    d.ellipse([cx-r, cy-r, cx+r, cy+r], outline=WHITE, width=int(r*0.10))
    aw = int(r*0.42)
    d.rectangle([cx-aw//3, cy-int(r*0.42), cx+aw//3, cy+int(r*0.10)], fill=WHITE)
    d.polygon([(cx-aw*0.62, cy-int(r*0.02)), (cx+aw*0.62, cy-int(r*0.02)),
               (cx, cy+int(r*0.46))], fill=WHITE)
    d.rectangle([cx-int(r*0.52), cy+int(r*0.52), cx+int(r*0.52), cy+int(r*0.60)], fill=WHITE)


def ear(d, tip, base_in, base_out, fill, inner=None):
    d.polygon([tip, base_in, base_out], fill=fill)
    if inner:
        # inner ear (scaled toward centroid)
        cxp = (tip[0]+base_in[0]+base_out[0])/3
        cyp = (tip[1]+base_in[1]+base_out[1])/3
        pts = [((p[0]*0.45+cxp*0.55), (p[1]*0.45+cyp*0.55)) for p in (tip, base_in, base_out)]
        d.polygon(pts, fill=inner)


def cat_features(d, cx, cy, r, eye=INK, happy=False):
    # eyes
    ex = int(r*0.42); ey = cy - int(r*0.05); er = int(r*0.14)
    if happy:
        for sx in (-1, 1):
            d.arc([cx+sx*ex-er, ey-er, cx+sx*ex+er, ey+er], 200, 340, fill=eye, width=int(r*0.06))
    else:
        for sx in (-1, 1):
            d.ellipse([cx+sx*ex-er, ey-int(er*1.25), cx+sx*ex+er, ey+int(er*1.25)], fill=eye)
    # nose
    nx, ny = cx, cy + int(r*0.16)
    d.polygon([(nx-int(r*0.09), ny), (nx+int(r*0.09), ny), (nx, ny+int(r*0.11))],
              fill=(255, 120, 140, 255))
    # mouth
    d.arc([nx-int(r*0.16), ny, nx, ny+int(r*0.24)], 20, 160, fill=eye, width=int(r*0.045))
    d.arc([nx, ny, nx+int(r*0.16), ny+int(r*0.24)], 20, 160, fill=eye, width=int(r*0.045))
    # whiskers
    for sx in (-1, 1):
        for k, yy in enumerate((-0.02, 0.10, 0.22)):
            d.line([(cx+sx*int(r*0.30), cy+int(r*(0.10+yy*0.0))),
                    (cx+sx*int(r*0.95), cy+int(r*(yy)))], fill=eye, width=int(r*0.03))


def variant_white_cat():
    """White cat, red left ear + blue right ear (Switch), navy bg, download badge."""
    img = canvas((37, 49, 71), (13, 20, 34))
    d = ImageDraw.Draw(img)
    cx, cy, r = S//2, int(S*0.48), int(S*0.27)
    # ears (colored) behind head
    ear(d, (cx-int(r*1.05), cy-int(r*1.35)), (cx-int(r*0.15), cy-int(r*0.55)),
        (cx-int(r*0.95), cy-int(r*0.35)), NEON_RED, inner=(255, 150, 160, 255))
    ear(d, (cx+int(r*1.05), cy-int(r*1.35)), (cx+int(r*0.15), cy-int(r*0.55)),
        (cx+int(r*0.95), cy-int(r*0.35)), NEON_BLUE, inner=(150, 225, 240, 255))
    d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=WHITE)
    cat_features(d, cx, cy, r, eye=INK)
    download_badge(img, int(S*0.72), int(S*0.74), int(S*0.155))
    return img


def variant_split_cat():
    """Face split red|blue (Joy-Con), white muzzle + features, dark bg."""
    img = canvas((24, 28, 40), (10, 12, 20))
    d = ImageDraw.Draw(img)
    cx, cy, r = S//2, int(S*0.47), int(S*0.28)
    # ears
    ear(d, (cx-int(r*1.05), cy-int(r*1.3)), (cx-int(r*0.1), cy-int(r*0.5)),
        (cx-int(r*0.9), cy-int(r*0.3)), NEON_RED, inner=(255, 150, 160, 255))
    ear(d, (cx+int(r*1.05), cy-int(r*1.3)), (cx+int(r*0.1), cy-int(r*0.5)),
        (cx+int(r*0.9), cy-int(r*0.3)), NEON_BLUE, inner=(150, 225, 240, 255))
    # split head
    box = [cx-r, cy-r, cx+r, cy+r]
    d.pieslice(box, 90, 270, fill=NEON_RED)
    d.pieslice(box, 270, 90, fill=NEON_BLUE)
    # white muzzle patch
    d.ellipse([cx-int(r*0.55), cy-int(r*0.02), cx+int(r*0.55), cy+int(r*0.72)], fill=WHITE)
    cat_features(d, cx, cy, r, eye=WHITE)
    # re-draw nose/mouth in ink on the white muzzle for contrast
    nx, ny = cx, cy + int(r*0.16)
    d.polygon([(nx-int(r*0.09), ny), (nx+int(r*0.09), ny), (nx, ny+int(r*0.11))],
              fill=(255, 90, 120, 255))
    d.arc([nx-int(r*0.16), ny, nx, ny+int(r*0.24)], 20, 160, fill=INK, width=int(r*0.045))
    d.arc([nx, ny, nx+int(r*0.16), ny+int(r*0.24)], 20, 160, fill=INK, width=int(r*0.045))
    download_badge(img, int(S*0.73), int(S*0.75), int(S*0.15))
    return img


def variant_cat_console():
    """Cat ears + face peeking over a Switch console; red/blue joy-cons."""
    img = canvas((59, 130, 246), (37, 20, 90))
    d = ImageDraw.Draw(img)
    # console
    cx, cy = S//2, int(S*0.6)
    w, h = int(S*0.66), int(S*0.34)
    jw = int(w*0.2)
    d.rounded_rectangle([cx-w//2, cy-h//2, cx-w//2+jw, cy+h//2], radius=jw//2, fill=NEON_RED)
    d.rounded_rectangle([cx+w//2-jw, cy-h//2, cx+w//2, cy+h//2], radius=jw//2, fill=NEON_BLUE)
    d.rounded_rectangle([cx-w//2+jw-6, cy-h//2, cx+w//2-jw+6, cy+h//2], radius=int(h*0.12), fill=WHITE)
    # cat face on the screen
    fr = int(h*0.42)
    fcx, fcy = cx, cy
    ear(d, (fcx-int(fr*1.1), fcy-int(fr*1.5)), (fcx-int(fr*0.15), fcy-int(fr*0.7)),
        (fcx-int(fr*0.95), fcy-int(fr*0.5)), NEON_RED)
    ear(d, (fcx+int(fr*1.1), fcy-int(fr*1.5)), (fcx+int(fr*0.15), fcy-int(fr*0.7)),
        (fcx+int(fr*0.95), fcy-int(fr*0.5)), NEON_BLUE)
    cat_features(d, fcx, fcy, fr, eye=INK)
    # download badge
    download_badge(img, int(S*0.73), int(S*0.30), int(S*0.135))
    return img


def finish(img, name):
    img.resize((256, 256), Image.LANCZOS).save(OUT / f"{name}_256.png")
    img.resize((512, 512), Image.LANCZOS).save(OUT / f"{name}.png")
    print("wrote", OUT / f"{name}.png")


if __name__ == "__main__":
    finish(variant_white_cat(), "cat1_white")
    finish(variant_split_cat(), "cat2_split")
    finish(variant_cat_console(), "cat3_console")
    print("done")
