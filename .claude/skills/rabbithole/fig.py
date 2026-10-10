#!/usr/bin/env python3
"""Prepare a reference figure for a dive: render, trim whitespace, downscale, compress.

  python3 fig.py <input.pdf|.png|.jpg|.webp> <dives/.../img/fig/name.png> [--trim L,B,R,T] [--page N] [--max 1400]

--trim takes LaTeX \\includegraphics trim values in points (left,bottom,right,top), so a figure that the
paper crops in its .tex source can be cropped the same way. PDFs are rendered with pdftoppm (poppler)
or, if missing, macOS sips. Output is a palette PNG, typically 20-80 KB. Needs Pillow.

Only feed it files from sources whose license allows reuse (see SKILL.md, "Reference figures").
"""
import argparse
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageChops, ImageOps

DPI = 220


def render_pdf(pdf, page, tmp):
    out = pathlib.Path(tmp) / "page"
    if shutil.which("pdftoppm"):
        subprocess.run(["pdftoppm", "-png", "-r", str(DPI), "-f", str(page), "-l", str(page), "-singlefile",
                        str(pdf), str(out)], check=True)
        return out.with_suffix(".png")
    if shutil.which("sips"):
        png = out.with_suffix(".png")
        subprocess.run(["sips", "-s", "format", "png", "-s", "dpiWidth", str(DPI), "-s", "dpiHeight", str(DPI),
                        str(pdf), "--out", str(png)], check=True, capture_output=True)
        return png
    sys.exit("need pdftoppm (brew install poppler / apt install poppler-utils) or macOS sips to render PDFs")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--trim", help="L,B,R,T in points, like LaTeX trim={L B R T}")
    ap.add_argument("--page", type=int, default=1)
    ap.add_argument("--max", type=int, default=1400, help="max width in px")
    a = ap.parse_args()
    src = pathlib.Path(a.src)
    with tempfile.TemporaryDirectory() as tmp:
        path = render_pdf(src, a.page, tmp) if src.suffix.lower() == ".pdf" else src
        im = Image.open(path)
        im.load()
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, "white")
        im = Image.alpha_composite(bg, im)
    im = im.convert("RGB")
    if a.trim:
        l, b, r, t = (float(x) * DPI / 72 for x in a.trim.split(","))
        if src.suffix.lower() != ".pdf":
            l = b = r = t = 0  # trim only meaningful for vector sources rendered at DPI
            print("note: --trim ignored for raster input", file=sys.stderr)
        im = im.crop((int(l), int(t), int(im.width - r), int(im.height - b)))
    # trim near-white margins
    mask = ImageChops.difference(im, Image.new("RGB", im.size, "white")).convert("L").point(lambda p: 255 if p > 10 else 0)
    bbox = mask.getbbox()
    if bbox:
        im = im.crop(bbox)
    im = ImageOps.expand(im, border=max(8, int(max(im.size) * 0.02)), fill="white")
    if im.width > a.max:
        im = im.resize((a.max, round(im.height * a.max / im.width)), Image.LANCZOS)
    dst = pathlib.Path(a.dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.quantize(colors=128, method=Image.Quantize.MEDIANCUT).save(dst, optimize=True)
    kb = os.path.getsize(dst) // 1024
    print(f"{dst} {im.width}x{im.height} {kb} KB" + ("  (large: consider --max 1000)" if kb > 250 else ""))


if __name__ == "__main__":
    main()
