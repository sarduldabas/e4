import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_file() -> None:
    """Tiny .env loader (no extra dependency). Real environment variables win."""
    p = Path(".env")
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            os.environ.setdefault(k.strip(), v)


@dataclass
class Settings:
    agents_url: str = "http://localhost:8002"
    agents_timeout: float = 30.0
    agent_run_timeout: float = 180.0  # pipeline agents read whole documents; a model call can take a while
    cors_origins: list[str] = field(default_factory=lambda: [
        "http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173", "null"])
    data_dir: Path = Path("./data")
    database_url: str | None = None  # default: sqlite file in data_dir; set to a postgresql+psycopg://... URL later
    allow_web: bool = True  # cited public pages are fetched and read in full; ALLOW_WEB=false switches it off (the search itself runs in Foundry)
    max_upload_mb: int = 50
    parallel_sections: int = 4
    parallel_calls: int = 6  # agent calls made at the same time while reading and extracting
    max_analysis_rounds: int = 2
    gap_rounds: int = 1  # extra research rounds after the first reading, aimed at what is still missing
    max_assets_analysed: int = 60  # pictures per report that the vision model looks at
    max_vision_pages: int = 60  # pages and pictures per file that may be read by the vision model
    extract_batch_chars: int = 16000  # text given to the evidence extractor per call
    max_extract_chars: int = 900000  # per source; beyond this the passages most relevant to the outline are read first
    passage_chars: int = 60000  # raw text from the sources that the section analyst may read per section
    demo_dir: str = ""
    seed_sample_reports: bool = False  # SEED_SAMPLE_REPORTS=true adds three empty sample rows to the report list (the committees are always there)

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{(Path(self.data_dir) / 'coe4.db').resolve().as_posix()}"


def load_settings() -> Settings:
    _env_file()
    s = Settings()
    s.agents_url = os.environ.get("AGENTS_URL", s.agents_url).rstrip("/")
    s.agents_timeout = float(os.environ.get("AGENTS_TIMEOUT_SECONDS", s.agents_timeout))
    s.agent_run_timeout = float(os.environ.get("AGENT_RUN_TIMEOUT_SECONDS", s.agent_run_timeout))
    if "CORS_ORIGINS" in os.environ:
        s.cors_origins = [o.strip() for o in os.environ["CORS_ORIGINS"].split(",") if o.strip()]
    s.data_dir = Path(os.environ.get("DATA_DIR", str(s.data_dir)))
    s.database_url = os.environ.get("DATABASE_URL") or None
    s.allow_web = os.environ.get("ALLOW_WEB", "true").lower() in ("1", "true", "yes")
    s.seed_sample_reports = os.environ.get("SEED_SAMPLE_REPORTS", "false").lower() in ("1", "true", "yes")
    s.max_upload_mb = int(os.environ.get("MAX_UPLOAD_MB", s.max_upload_mb))
    s.parallel_sections = int(os.environ.get("PARALLEL_SECTIONS", s.parallel_sections))
    s.parallel_calls = int(os.environ.get("PARALLEL_CALLS", s.parallel_calls))
    s.gap_rounds = int(os.environ.get("GAP_ROUNDS", s.gap_rounds))
    s.max_assets_analysed = int(os.environ.get("MAX_ASSETS_ANALYSED", s.max_assets_analysed))
    s.max_vision_pages = int(os.environ.get("MAX_VISION_PAGES", s.max_vision_pages))
    s.extract_batch_chars = int(os.environ.get("EXTRACT_BATCH_CHARS", s.extract_batch_chars))
    s.max_extract_chars = int(os.environ.get("MAX_EXTRACT_CHARS", s.max_extract_chars))
    s.passage_chars = int(os.environ.get("PASSAGE_CHARS", s.passage_chars))
    return s
