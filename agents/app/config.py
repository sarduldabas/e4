"""Settings of the agents service. Read from environment variables; a `.env` file next to `app/` fills in the rest.

Real environment variables win over the file. Secrets (keys) are never logged or returned by any endpoint.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"  # agents/.env, no matter where the server is started from


def load_env_file(path: Path = ENV_FILE) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")  # allow trailing comments and quotes
        os.environ.setdefault(key.strip(), value)


def _clean_endpoint(value: str) -> str:
    """Accept what people paste: trailing slash, or a URL that already ends in /openai/v1 or /chat/completions."""
    v = value.strip().rstrip("/")
    for suffix in ("/chat/completions", "/openai/v1", "/openai"):
        if v.lower().endswith(suffix):
            v = v[: -len(suffix)]
    return v.rstrip("/")


def _flag(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class LlmSettings:
    endpoint: str = ""  # https://<resource>.openai.azure.com  (or .services.ai.azure.com / .cognitiveservices.azure.com)
    api_key: str = ""
    deployment: str = ""  # the deployment (model) name in Foundry
    api_version: str = ""  # empty = the v1 API (recommended); set e.g. 2024-10-21 to use the classic Azure API
    use_entra_id: bool = False  # sign in with the Azure identity of the machine instead of an API key
    entra_scope: str = "https://cognitiveservices.azure.com/.default"  # Foundry project endpoints may need https://ai.azure.com/.default
    entra_browser: bool = True  # Entra ID only: when `az login` / VS Code / env sign-in is not available, open a browser tab to sign in
    tenant_id: str = ""  # Entra ID only: optional tenant (directory) id for the browser sign-in
    timeout_seconds: float = 20.0
    tier_deployments: dict = field(default_factory=dict)  # optional: small / standard / strong / vision -> deployment name

    def deployment_for(self, tier: str | None) -> str:
        """Deployment for a model tier. Tiers without their own setting use AZURE_OPENAI_DEPLOYMENT."""
        return (self.tier_deployments.get(tier or "") or self.deployment).strip()

    @property
    def configured(self) -> bool:
        if not (self.endpoint and self.deployment):
            return False
        return bool(self.api_key) or self.use_entra_id


@dataclass(frozen=True)
class Settings:
    agent_mode: str = "auto"  # auto: LLM when configured, else rules | llm: LLM, rules as fallback | rules: never call a model
    llm: LlmSettings = LlmSettings()


def load_settings() -> Settings:
    load_env_file()
    env = os.environ.get
    mode = env("AGENT_MODE", "auto").strip().lower()
    if mode not in {"auto", "llm", "rules"}:
        mode = "auto"
    return Settings(
        agent_mode=mode,
        llm=LlmSettings(
            endpoint=_clean_endpoint(env("AZURE_OPENAI_ENDPOINT", "")),
            api_key=env("AZURE_OPENAI_API_KEY", "").strip(),
            deployment=env("AZURE_OPENAI_DEPLOYMENT", "").strip(),
            api_version=env("AZURE_OPENAI_API_VERSION", "").strip(),
            use_entra_id=_flag("AZURE_USE_ENTRA_ID"),
            entra_scope=env("AZURE_OPENAI_ENTRA_SCOPE", "").strip() or LlmSettings.entra_scope,
            entra_browser=_flag("AZURE_ENTRA_BROWSER", True),
            tenant_id=env("AZURE_TENANT_ID", "").strip(),
            timeout_seconds=float(env("LLM_TIMEOUT_SECONDS", "20") or 20),
            tier_deployments={t: env(f"AZURE_OPENAI_DEPLOYMENT_{t.upper()}", "").strip() for t in ("small", "standard", "strong", "vision")},
        ),
    )
