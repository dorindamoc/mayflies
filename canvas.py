"""Draws SVG into a picture the model can look at."""

from __future__ import annotations

import re
import struct

MAX_SVG_BYTES = 200_000
MIN_IMAGE_TOKENS = 66
_FORBIDDEN = re.compile(r"<\s*(image|script|foreignObject|iframe|embed|object)\b", re.I)
_HREF = re.compile(r"""(?:xlink:)?href\s*=\s*["']([^"']*)["']""", re.I)


class CanvasError(ValueError):
    pass


def check_svg(svg: str) -> None:
    """Refuse SVG that could read files or reach beyond the drawing: only same-document references are allowed."""
    if len(svg.encode()) > MAX_SVG_BYTES:
        raise CanvasError(f"SVG too large (max {MAX_SVG_BYTES} bytes).")
    found = _FORBIDDEN.search(svg)
    if found:
        raise CanvasError(f"<{found.group(1)}> is not allowed in a drawing; draw with shapes, paths and text.")
    for ref in _HREF.findall(svg):
        if not ref.startswith("#"):
            raise CanvasError("references to other files or addresses are not allowed; only #id references.")


def png_size(png: bytes) -> tuple:
    return struct.unpack(">II", png[16:24])


def image_tokens(width: int, height: int) -> int:
    """What a picture costs in context, measured on qwen3.8: about one token per 32x32 pixels, at least 66."""
    return max(MIN_IMAGE_TOKENS, width * height // 1024 + 2)


def render_svg(svg: str, size: int) -> bytes:
    """A PNG no wider and no taller than size pixels."""
    import resvg_py
    check_svg(svg)
    try:
        png = bytes(resvg_py.svg_to_bytes(svg_string=svg, width=size))
        if png_size(png)[1] > size:
            png = bytes(resvg_py.svg_to_bytes(svg_string=svg, height=size))
    except Exception as e:
        raise CanvasError(f"could not draw the SVG: {e}")
    return png
