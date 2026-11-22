import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_file() -> None:
    """Tiny .env loader (no extra dependency). Real environment variables win."""
    p = Path(".env")
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


@dataclass
class Settings:
    agents_url: str = "http://localhost:8002"
    agents_timeout: float = 8.0
    cors_origins: list[str] = field(default_factory=lambda: [
        "http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173", "null"])
    data_dir: Path = Path("./data")


def load_settings() -> Settings:
    _env_file()
    s = Settings()
    s.agents_url = os.environ.get("AGENTS_URL", s.agents_url).rstrip("/")
    s.agents_timeout = float(os.environ.get("AGENTS_TIMEOUT_SECONDS", s.agents_timeout))
    if "CORS_ORIGINS" in os.environ:
        s.cors_origins = [o.strip() for o in os.environ["CORS_ORIGINS"].split(",") if o.strip()]
    s.data_dir = Path(os.environ.get("DATA_DIR", str(s.data_dir)))
    return s
