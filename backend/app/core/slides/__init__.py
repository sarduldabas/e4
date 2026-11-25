"""Slides: one specification (JSON) that the web page shows and the PowerPoint file is built from."""
from .pack import merge, plan as pack_plan
from .render_pptx import build_pptx
from .spec import claim_ids_of, layouts, normalise, numbers_not_in, parse_numbers, scrub
from .theme import theme_of

__all__ = ["build_pptx", "merge", "pack_plan", "claim_ids_of", "layouts", "normalise", "numbers_not_in", "parse_numbers", "scrub", "theme_of"]
