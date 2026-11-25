"""Pictures, plain text formats, archives. Plus the one place that decides whether a picture goes to the vision model."""
from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from pathlib import Path

from .model import Chunk, Image, Options, Parsed, Table, VisionTask
from .text import cell, clean, decode, rows_to_text, split, strip_html


def dims(blob: bytes) -> tuple[int | None, int | None]:
    try:
        from PIL import Image as PILImage

        with PILImage.open(io.BytesIO(blob)) as im:
            return im.size
    except Exception:  # noqa: BLE001
        return None, None


def jpeg_of(blob: bytes, max_px: int = 1600) -> tuple[bytes, int, int] | None:
    """Normalise any picture to an upright JPEG that fits the vision model."""
    try:
        from PIL import Image as PILImage, ImageOps

        with PILImage.open(io.BytesIO(blob)) as im:
            im = ImageOps.exif_transpose(im)
            if im.mode in ("RGBA", "LA", "P"):
                bg = PILImage.new("RGB", im.size, "white")
                rgba = im.convert("RGBA")
                bg.paste(rgba, mask=rgba.split()[-1])
                im = bg
            im = im.convert("RGB")
            im.thumbnail((max_px, max_px))
            out = io.BytesIO()
            im.save(out, "JPEG", quality=80)
            return out.getvalue(), im.width, im.height
    except Exception:  # noqa: BLE001
        return None


def add_picture(p: Parsed, blob: bytes, ext: str, locator: str, caption: str, opts: Options, *, always_vision: bool = False, hint: str = "") -> None:
    """Keep the picture as an asset; send it to the vision model when it is big enough to carry content (a chart, a scan, a photo of a page)."""
    w, h = dims(blob)
    if w and h and (w < 120 or h < 80):  # bullets, icons, lines
        return
    p.images.append(Image(blob, ext or "png", w, h, caption, locator))
    big = bool(w and h and w >= 380 and h >= 220 and len(blob) >= 12_000)
    if (always_vision or big) and len(p.vision) < opts.max_vision_pages:
        j = jpeg_of(blob, opts.max_image_px)
        if j:
            p.vision.append(VisionTask(f"i{len(p.vision) + 1}", locator, j[0], "image", hint=hint or caption))


def read_image(data: bytes, opts: Options | None = None, name: str = "") -> Parsed:
    opts = opts or Options()
    p = Parsed("image")
    try:
        from PIL import Image as PILImage

        with PILImage.open(io.BytesIO(data)) as im:
            frames = getattr(im, "n_frames", 1)
            fmt = (im.format or "png").lower()
            if frames > 1 and fmt in ("tiff", "mpo"):
                for f in range(min(frames, opts.max_vision_pages)):
                    im.seek(f)
                    buf = io.BytesIO()
                    im.convert("RGB").save(buf, "PNG")
                    add_picture(p, buf.getvalue(), "png", f"Seite {f + 1}", "", opts, always_vision=True, hint=name)
                p.stats["frames"] = frames
                return p
    except Exception:  # noqa: BLE001
        pass
    if not dims(data)[0]:
        raise ValueError("the picture cannot be opened")
    w, h = dims(data)
    j = jpeg_of(data, opts.max_image_px)
    p.images.append(Image(data, "png", w, h, "", "Bild"))
    if j:
        p.vision.append(VisionTask("i1", "Bild", j[0], "image", hint=name))
    return p


def read_text(data: bytes, kind: str = "txt") -> Parsed:
    t = decode(data)
    if kind == "json":
        try:
            t = json.dumps(json.loads(t), ensure_ascii=False, indent=1)
        except ValueError:
            pass
    p = Parsed(kind)
    p.chunks = split("Text", t)
    return p


def read_csv(data: bytes) -> Parsed:
    text = decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text), dialect)]
    p = Parsed("csv", tables=[Table("", rows[:60], "Tabelle")])
    if not rows:
        return p
    header, cur, start = rows[0], [], 1
    size = 0
    for i, r in enumerate(rows[1:], 2):
        line = " | ".join(c for c in r if c != "")
        if cur and size + len(line) > 1800:
            p.chunks.append(Chunk(f"Zeilen {start}-{i - 1}", rows_to_text([header] + cur)))
            cur, size, start = [], 0, i
        cur.append(r)
        size += len(line) + 1
    if cur or len(rows) == 1:
        p.chunks.append(Chunk(f"Zeilen {start}-{len(rows)}", rows_to_text([header] + cur)))
    p.stats["rows"] = len(rows)
    return p


def read_html(data: bytes) -> Parsed:
    raw = decode(data)
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
    p = Parsed("html", title=strip_html(m.group(1)) if m else "")
    p.chunks = split("Seite", strip_html(raw))
    return p


def read_xml(data: bytes) -> Parsed:
    raw = decode(data)
    p = Parsed("xml")
    p.chunks = split("Text", strip_html(raw))
    return p


def read_zip(data: bytes, parse_member, opts: Options, depth: int) -> Parsed:
    """Archives are opened (with limits against zip bombs) and every member is read like an upload."""
    p = Parsed("zip")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise ValueError("the archive is damaged") from e
    infos = [i for i in zf.infolist() if not i.is_dir() and not Path(i.filename).name.startswith(("~$", ".", "__MACOSX"))]
    if sum(i.file_size for i in infos) > opts.max_zip_mb * 1024 * 1024:
        raise ValueError(f"the archive is larger than {opts.max_zip_mb} MB when unpacked")
    if len(infos) > opts.max_zip_files:
        p.warnings.append(f"only the first {opts.max_zip_files} of {len(infos)} files were read")
        infos = infos[: opts.max_zip_files]
    for i in infos:
        try:
            child = parse_member(Path(i.filename).name, zf.read(i), depth + 1)
        except Exception as e:  # noqa: BLE001  one bad member must not stop the archive
            p.warnings.append(f"{i.filename}: not read ({e.__class__.__name__}: {str(e)[:120]})")
            continue
        p.absorb(child, f"Datei „{i.filename}“")
    p.stats["members"] = len(infos)
    return p
