#!/usr/bin/env python3
"""Redact player names and other identifying regions from a screenshot.

Screenshots of the HUD are only useful over a *real* table window, and a real
table window carries other people's screen names. This paints chosen rectangles
out of an image before it is published to the wiki, and strips the metadata the
capture tool wrote into the file.

    python tools/anonymize_screenshot.py table.png -o table-wiki.png \
        --box 120,340,180,22 --box 410,190,180,22

Coordinates are ``x,y,width,height`` in pixels from the top-left. Pass
``--relative`` to give them as fractions of the image instead (``0.1,0.3,0.2,
0.04``), which survives rescaling the source capture.

Why no blur
-----------
Gaussian blur is a linear, low-pass filter: it attenuates detail rather than
discarding it, and text is the easiest case to bring back -- a short screen name
drawn from a small alphabet in a known font can be recovered by deconvolution or
simply by re-rendering candidates until one blurs to the same pixels. The same
argument applies to fine-grained pixelation, which is just box-filter blur with
a coarse grid: if a glyph spans several blocks, the block averages still encode
which glyph it was.

So this tool offers two modes and neither is a blur:

``fill`` (default)
    Paint the region a solid colour. Nothing survives, and that is the point.

``pixelate``
    Reduce the region to a handful of blocks. Kept for when a flat rectangle
    would hide the layout being illustrated. ``--block`` is a *minimum*: the
    block size is enlarged as needed so that no region is ever reduced to more
    than :data:`MAX_BLOCKS_PER_AXIS` blocks on either axis, because that is the
    grid coarseness at which per-block averages stop carrying the glyph.

Both modes rewrite the pixels, so the redaction survives being cropped,
re-encoded, or screenshotted again.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - depends on the environment
    print("Pillow is required: pip install pillow (it also ships with matplotlib)", file=sys.stderr)
    raise SystemExit(1) from None

MAX_BLOCKS_PER_AXIS = 4
"""Coarsest grid a pixelated region may keep, per axis.

Four blocks across a name plate leaves the eye a smear and leaves an attacker
sixteen averages for a string of several characters -- far less information than
the string contains.
"""

DEFAULT_FILL = "#101418"
"""A dark neutral, so redactions read as part of a poker client rather than as
white holes punched in the picture."""


@dataclass(frozen=True)
class Box:
    """A rectangle to redact, in absolute pixels."""

    x: int
    y: int
    width: int
    height: int

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        """``(left, upper, right, lower)`` as Pillow wants it."""
        return (self.x, self.y, self.x + self.width, self.y + self.height)

    def clamped(self, image_width: int, image_height: int) -> Box | None:
        """This box cropped to the image, or None when it falls entirely outside."""
        left = max(0, min(self.x, image_width))
        upper = max(0, min(self.y, image_height))
        right = max(0, min(self.x + self.width, image_width))
        lower = max(0, min(self.y + self.height, image_height))
        if right <= left or lower <= upper:
            return None
        return Box(left, upper, right - left, lower - upper)


def parse_box(spec: str, *, relative: bool, size: tuple[int, int]) -> Box:
    """Turn an ``x,y,w,h`` argument into a :class:`Box`.

    With ``relative``, the four numbers are fractions of the image's width and
    height rather than pixels.
    """
    parts = spec.split(",")
    if len(parts) != 4:
        msg = f"expected x,y,width,height -- got {spec!r}"
        raise argparse.ArgumentTypeError(msg)
    try:
        numbers = [float(part) for part in parts]
    except ValueError:
        msg = f"box coordinates must be numbers -- got {spec!r}"
        raise argparse.ArgumentTypeError(msg) from None

    if relative:
        width, height = size
        scales = (width, height, width, height)
        numbers = [value * scale for value, scale in zip(numbers, scales, strict=True)]

    x, y, w, h = (int(round(value)) for value in numbers)
    if w <= 0 or h <= 0:
        msg = f"box width and height must be positive -- got {spec!r}"
        raise argparse.ArgumentTypeError(msg)
    return Box(x, y, w, h)


def block_size_for(box: Box, requested: int) -> int:
    """The block size to pixelate ``box`` with, never finer than the cap.

    ``requested`` is a floor, not a setting: a caller asking for 8-pixel blocks
    on a 400-pixel-wide plate would leave fifty blocks across a name, which is a
    thumbnail of the name rather than a redaction.
    """
    needed = max(box.width, box.height) / MAX_BLOCKS_PER_AXIS
    return max(1, int(max(requested, needed)))


def pixelate(image: Image.Image, box: Box, requested_block: int) -> None:
    """Replace ``box`` in ``image`` with a coarse grid of block averages."""
    block = block_size_for(box, requested_block)
    region = image.crop(box.bounds)
    columns = max(1, region.width // block)
    rows = max(1, region.height // block)
    # BOX on the way down averages each block; NEAREST on the way up keeps the
    # blocks flat instead of interpolating detail back in.
    small = region.resize((columns, rows), Image.Resampling.BOX)
    image.paste(small.resize(region.size, Image.Resampling.NEAREST), box.bounds)


def fill(image: Image.Image, box: Box, colour: str) -> None:
    """Paint ``box`` in ``image`` a solid colour."""
    image.paste(Image.new(image.mode, (box.width, box.height), colour), box.bounds)


def redact(image: Image.Image, boxes: list[Box], *, mode: str, block: int, colour: str) -> int:
    """Apply every box that intersects the image. Returns how many were applied."""
    applied = 0
    for box in boxes:
        clamped = box.clamped(image.width, image.height)
        if clamped is None:
            print(f"warning: box {box.x},{box.y},{box.width},{box.height} is outside the image", file=sys.stderr)
            continue
        if mode == "pixelate":
            pixelate(image, clamped, block)
        else:
            fill(image, clamped, colour)
        applied += 1
    return applied


def save_without_metadata(image: Image.Image, path: Path) -> None:
    """Write the image with no EXIF, ICC or PNG text chunks carried over.

    Capture tools record the machine name, the window title and sometimes the
    file path in there, none of which is visible in the picture that gets
    reviewed before publishing.
    """
    clean = Image.new(image.mode, image.size)
    clean.putdata(list(image.getdata()))
    clean.save(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("source", type=Path, help="image to redact")
    parser.add_argument("-o", "--output", type=Path, help="where to write (default: <source>-anon<ext>)")
    parser.add_argument(
        "--box",
        action="append",
        default=[],
        metavar="X,Y,W,H",
        help="rectangle to redact; repeat for each one",
    )
    parser.add_argument(
        "--relative",
        action="store_true",
        help="read box coordinates as fractions of the image size rather than pixels",
    )
    parser.add_argument(
        "--mode",
        choices=("fill", "pixelate"),
        default="fill",
        help="fill paints a solid rectangle (default); pixelate keeps a coarse shape",
    )
    parser.add_argument(
        "--block",
        type=int,
        default=16,
        help="minimum pixelation block size; raised automatically when a region needs it",
    )
    parser.add_argument("--colour", "--color", dest="colour", default=DEFAULT_FILL, help="fill colour")
    args = parser.parse_args(argv)

    if not args.source.is_file():
        print(f"no such image: {args.source}", file=sys.stderr)
        return 1
    if not args.box:
        print("nothing to redact: pass at least one --box X,Y,W,H", file=sys.stderr)
        return 1

    with Image.open(args.source) as opened:
        image = opened.convert("RGB")

    try:
        boxes = [parse_box(spec, relative=args.relative, size=image.size) for spec in args.box]
    except argparse.ArgumentTypeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    applied = redact(image, boxes, mode=args.mode, block=args.block, colour=args.colour)
    if not applied:
        print("no box intersected the image; nothing written", file=sys.stderr)
        return 1

    destination = args.output or args.source.with_name(f"{args.source.stem}-anon{args.source.suffix}")
    save_without_metadata(image, destination)
    print(f"{applied} region(s) redacted with '{args.mode}' -> {destination}")
    print("Check the result before publishing: this tool paints where it is told, it does not find names.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
