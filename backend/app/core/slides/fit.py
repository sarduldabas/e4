"""Text fitting. Both renderers (PowerPoint and the web page) use the font sizes computed here, so a slide looks the same in both and
never overflows. Estimation, not measurement: average glyph width 0.54 em (a little wider than Arial's to be safe for German words)."""
from __future__ import annotations

import math

CHAR_W = 0.54
LINE_H = 1.25
PAD = 14


def lines(text: str, size: float, width: float) -> int:
    cpl = max(4, int(width / (size * CHAR_W)))
    return sum(max(1, math.ceil(len(part) / cpl)) for part in (text.split("\n") or [""]))


def bullets_size(items: list[str], w: float, h: float, sizes=(26, 24, 22, 20, 18, 17, 16, 15, 14, 13, 12)) -> tuple[int, bool]:
    """Largest font size at which all bullets fit the box. Returns (size, fits)."""
    if not items:
        return sizes[0], True
    for fs in sizes:
        inner = w - 2 * PAD - fs * 1.4  # bullet indent
        total = sum(lines(t, fs, inner) * fs * LINE_H for t in items) + (len(items) - 1) * fs * 0.6 + 2 * PAD
        if total <= h:
            return fs, True
    return sizes[-1], False


def callout_size(title: str, text: str, w: float, h: float, sizes=(30, 28, 26, 24, 22, 20, 18, 16, 15, 14)) -> tuple[int, bool]:
    for fs in sizes:
        inner = w - 2 * (PAD + 8)
        total = (lines(title, fs * 0.7, inner) * fs * 0.7 * LINE_H + 8 if title else 0) + lines(text, fs, inner) * fs * LINE_H + 2 * (PAD + 6)
        if total <= h:
            return fs, True
    return sizes[-1], False


def title_size(text: str, w: float, h: float, sizes=(34, 32, 30, 28, 26, 24, 22)) -> tuple[int, bool]:
    for fs in sizes:
        if lines(text, fs * 1.04, w) * fs * 1.2 <= h:  # titles are bold: a little wider
            return fs, True
    return sizes[-1], False


def kpi_sizes(n: int, w: float, items: list[tuple[str, str, str]]) -> tuple[int, int]:
    """(value font size, label font size) for n tiles in a row `w` wide; items are (value, unit, label)."""
    gap = 16
    tile = (w - gap * (n - 1)) / max(n, 1)
    vs = 52
    while vs > 22 and any((len(v) * vs * 0.58 + len(u) * vs * 0.36 + 10) > tile - 2 * PAD for v, u, _ in items):
        vs -= 2
    ls = 17
    while ls > 11 and any(lines(l, ls, tile - 2 * PAD) > 2 for _, _, l in items):
        ls -= 1
    return vs, ls


def table_size(header: list[str], rows: list[list[str]], w: float, h: float, sizes=(20, 18, 17, 16, 15, 14, 13, 12, 11, 10)) -> tuple[int, list[float], bool]:
    """(font size, column widths, fits). The first column gets more room; width is shared by text length."""
    cols = max([len(header)] + [len(r) for r in rows] or [1])
    weight = [1.0] * cols
    for ci in range(cols):
        longest = max([len((header[ci] if ci < len(header) else ""))] + [len(r[ci]) if ci < len(r) else 0 for r in rows])
        weight[ci] = min(max(longest, 6), 40) ** 0.7
    tot = sum(weight)
    widths = [w * x / tot for x in weight]
    for fs in sizes:
        total = 0.0
        for ri, row in enumerate([header] + rows):
            if not row and ri == 0:
                continue
            cell_h = max(lines(row[ci] if ci < len(row) else "", fs, widths[ci] - 16) for ci in range(cols)) * fs * LINE_H + 14
            total += cell_h
        if total <= h:
            return fs, widths, True
    return sizes[-1], widths, False
