"""What every reader returns. Readers are code: they take text, tables and pictures out of a file exactly as they are in it.

Pages and pictures that code cannot read (scans, photos, charts as pictures) are handed back as `VisionTask`s; the orchestrator
sends them to the vision model (the `document-reader` agent) and puts the transcription back with `apply_vision`.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Chunk:
    locator: str
    text: str
    ref: str | None = None  # id of the vision task this text stands in for (replaced when the vision result arrives)
    flags: tuple[str, ...] = ()  # "vision": text was transcribed by the vision model


@dataclass
class Image:
    data: bytes
    ext: str
    width: int | None
    height: int | None
    caption: str
    locator: str
    origin: str = "document"  # document | web
    rights: str = ""  # where a web picture comes from (the right to use it must be checked)
    context: str = ""  # text around it in the source


@dataclass
class ChartObj:
    """A chart whose numbers are known exactly because the file stores them (PowerPoint charts)."""
    locator: str
    title: str
    type: str  # column | bar | line | donut | stacked
    unit: str
    labels: list[str]
    series: list[dict]  # {"name", "values"}


@dataclass
class Table:
    caption: str
    rows: list[list[str]]
    locator: str


@dataclass
class VisionTask:
    key: str
    locator: str
    image: bytes  # JPEG
    reason: str  # scanned | figure | image | garbled
    hint: str = ""  # what the code already knows (file name, text layer, caption)
    existing_text: str = ""


@dataclass
class Parsed:
    kind: str
    chunks: list[Chunk] = field(default_factory=list)
    images: list[Image] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    charts: list[ChartObj] = field(default_factory=list)
    title: str = ""
    meta: dict = field(default_factory=dict)  # author, dates, mail headers ...
    warnings: list[str] = field(default_factory=list)
    vision: list[VisionTask] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def absorb(self, child: "Parsed", prefix: str) -> None:
        """Put an attachment / archive member into this document: its locators get the prefix, everything else is merged."""
        tag = f"{len(self.vision)}_{abs(hash(prefix)) % 10_000}"
        for c in child.chunks:
            self.chunks.append(Chunk(f"{prefix} › {c.locator}", c.text, f"{tag}:{c.ref}" if c.ref else None, c.flags))
        for t in child.tables:
            self.tables.append(Table(t.caption, t.rows, f"{prefix} › {t.locator}"))
        for c in child.charts:
            self.charts.append(ChartObj(f"{prefix} › {c.locator}", c.title, c.type, c.unit, c.labels, c.series))
        for im in child.images:
            self.images.append(Image(im.data, im.ext, im.width, im.height, im.caption, f"{prefix} › {im.locator}", im.origin, im.rights, im.context))
        for v in child.vision:
            self.vision.append(VisionTask(f"{tag}:{v.key}", f"{prefix} › {v.locator}", v.image, v.reason, v.hint, v.existing_text))
        self.warnings += [f"{prefix}: {w}" for w in child.warnings]


@dataclass
class Options:
    """Limits. They protect the machine, never the content: what is skipped is named in `Parsed.warnings`."""
    max_vision_pages: int = 60  # pages and pictures per file that may go to the vision model
    max_image_px: int = 1600  # longest side of a picture sent to the vision model
    table_seconds: float = 40.0  # time budget for table detection in one PDF
    max_pages: int = 3000
    max_rows: int = 60000  # spreadsheet rows read as text per workbook
    max_zip_files: int = 300
    max_zip_mb: int = 600
    max_depth: int = 3  # attachments inside attachments
    min_attachment_image_bytes: int = 15_000  # smaller inline pictures of mails are logos and signatures
