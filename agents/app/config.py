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
    """Accept what people paste: trailing slash, or a URL that already ends in /openai/v1, /responses or /chat/completions."""
    v = value.strip().rstrip("/")
    for suffix in ("/chat/completions", "/responses", "/openai/v1", "/openai"):
        if v.lower().endswith(suffix):
            v = v[: -len(suffix)]
    return v.rstrip("/")


def _first(*names: str, default: str = "") -> str:
    """First environment variable of these names that has a value (so the names other tools use also work)."""
    for n in names:
        v = os.environ.get(n, "").strip()
        if v:
            return v
    return default


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
    web_search_tool: str = "web_search_preview"  # tool type of the Foundry web search ("web_search" on newer API versions)
    auth_record: str = ""  # file that remembers which account signed in, so the browser sign-in is needed once, not at every start
    entra_browser: bool = True  # Entra ID only: when `az login` / VS Code / env sign-in is not available, open a browser tab to sign in
    tenant_id: str = ""  # Entra ID only: optional tenant (directory) id for the browser sign-in
    entra_scope_explicit: bool = False  # True when AZURE_OPENAI_ENTRA_SCOPE was set by the user
    timeout_seconds: float = 20.0
    tier_deployments: dict = field(default_factory=dict)  # optional: small / standard / strong / vision -> deployment name

    @property
    def scope(self) -> str:
        """Token scope. A Foundry *project* URL (.../api/projects/<name>) needs the AI scope; resource URLs use the cognitive services scope."""
        if self.entra_scope_explicit:
            return self.entra_scope
        return "https://ai.azure.com/.default" if "/api/projects/" in self.endpoint.lower() else self.entra_scope

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
    fallback: str = "rules"  # when a model call fails: "rules" = answer with the simple rules version (and say so) | "error" = fail loudly


def _endpoint_from_env() -> str:
    """The endpoint as pasted, or built from the Foundry resource and project names when only those are given."""
    ep = _first("AZURE_OPENAI_ENDPOINT", "AZURE_AI_PROJECT_ENDPOINT", "AZURE_AI_FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_PROJECT_ENDPOINT", "PROJECT_ENDPOINT")
    if ep:
        return _clean_endpoint(ep)
    res, proj = _first("AZURE_AI_FOUNDRY_RESOURCE", "AZURE_AI_RESOURCE_NAME"), _first("AZURE_AI_PROJECT_NAME", "AZURE_AI_PROJECT_ID", "FOUNDRY_PROJECT_ID")
    if res and proj:
        return f"https://{res}.services.ai.azure.com/api/projects/{proj}"
    if res:
        return f"https://{res}.openai.azure.com"
    return ""


def load_settings() -> Settings:
    load_env_file()
    env = os.environ.get
    mode = env("AGENT_MODE", "auto").strip().lower()
    if mode not in {"auto", "llm", "rules"}:
        mode = "auto"
    return Settings(
        agent_mode=mode,
        fallback="error" if env("AGENT_FALLBACK", "rules").strip().lower() == "error" else "rules",
        llm=LlmSettings(
            endpoint=_endpoint_from_env(),
            api_key=env("AZURE_OPENAI_API_KEY", "").strip(),
            deployment=_first("AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_DEPLOYMENT_NAME", "AZURE_AI_MODEL_DEPLOYMENT_NAME", "MODEL_DEPLOYMENT_NAME"),
            api_version=env("AZURE_OPENAI_API_VERSION", "").strip(),
            use_entra_id=_flag("AZURE_USE_ENTRA_ID", default=not env("AZURE_OPENAI_API_KEY", "").strip()),  # no key = sign in with the Azure account
            entra_scope=env("AZURE_OPENAI_ENTRA_SCOPE", "").strip() or LlmSettings.entra_scope,
            entra_scope_explicit=bool(env("AZURE_OPENAI_ENTRA_SCOPE", "").strip()),
            web_search_tool=env("AZURE_WEB_SEARCH_TOOL", "").strip() or LlmSettings.web_search_tool,
            auth_record=env("AZURE_AUTH_RECORD", "").strip() or str(ENV_FILE.parent / ".azure-auth-record.json"),
            entra_browser=_flag("AZURE_ENTRA_BROWSER", True),
            tenant_id=_first("AZURE_TENANT_ID", "AZURE_AI_TENANT_ID", "TENANT_ID"),
            timeout_seconds=float(env("LLM_TIMEOUT_SECONDS", "20") or 20),
            tier_deployments={t: env(f"AZURE_OPENAI_DEPLOYMENT_{t.upper()}", "").strip() for t in ("small", "standard", "strong", "vision")},
        ),
    )
