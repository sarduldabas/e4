"""Compatibility shim: the readers live in `app.core.ingest`."""
from .ingest import (CHUNK_CHARS, SUPPORTED, Chunk, Image, Options, Parsed, Table, VisionTask, apply_vision, kind_of, parse_bytes, read_template,  # noqa: F401
                     thumbnail_data_url)
