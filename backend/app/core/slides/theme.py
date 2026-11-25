"""Colours and fonts of a deck: the default theme, or the theme of an uploaded PowerPoint template."""
from __future__ import annotations

import io
import re
import zipfile

from .spec import default_theme


def _hex(v: str) -> str:
    return "#" + v.upper()


def _lum(h: str) -> float:
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def theme_of(template: bytes | None) -> dict:
    """The default theme, with colours and fonts taken from the template when it has a readable theme."""
    th = default_theme()
    th = {"colors": dict(th["colors"]), "palette": list(th["palette"]), "fonts": dict(th["fonts"]), "from_template": False}
    if not template:
        return th
    try:
        z = zipfile.ZipFile(io.BytesIO(template))
        name = next(n for n in z.namelist() if re.match(r"ppt/theme/theme\d+\.xml$", n))
        xml = z.read(name).decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        return th
    clr = {}
    for key in ("dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6"):
        m = re.search(rf"<a:{key}>\s*<a:(?:srgbClr val|sysClr val=\"[^\"]*\" lastClr)=\"([0-9A-Fa-f]{{6}})\"", xml)
        if m:
            clr[key] = _hex(m.group(1))
    if "accent1" in clr:
        pal = [clr[k] for k in ("accent1", "accent2", "accent3", "accent4", "accent5", "accent6") if k in clr]
        primary = clr["dk2"] if clr.get("dk2") and _lum(clr["dk2"]) < 0.35 else (clr["accent1"] if _lum(clr["accent1"]) < 0.5 else (clr.get("dk1") or th["colors"]["primary"]))
        th["colors"].update({"primary": primary, "accent": clr.get("accent2", clr["accent1"]) if primary == clr["accent1"] else clr["accent1"]})
        if clr.get("dk1"):
            th["colors"]["text"] = clr["dk1"] if _lum(clr["dk1"]) < 0.3 else th["colors"]["text"]
        th["palette"] = [primary] + [c for c in pal if c != primary][:5]
        th["from_template"] = True
    mf = re.search(r"<a:majorFont>\s*<a:latin typeface=\"([^\"]+)\"", xml)
    nf = re.search(r"<a:minorFont>\s*<a:latin typeface=\"([^\"]+)\"", xml)
    if mf and not mf.group(1).startswith("+"):
        th["fonts"]["heading"] = mf.group(1)
    if nf and not nf.group(1).startswith("+"):
        th["fonts"]["body"] = nf.group(1)
    return th
