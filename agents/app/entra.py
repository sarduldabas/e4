"""Sign in to Foundry / Azure OpenAI with the user's Azure account (Entra ID), and remember it.

Order of attempts, first one that works wins:
  1. what is already available on the machine: environment, managed identity, VS Code, Azure CLI (`az login`), Azure PowerShell, azd
  2. a browser tab (your normal browser, so smart card / SSO of the organisation work). The account that signed in is saved in a small
     file (no secrets) and the tokens are kept in the operating system's protected cache (Windows: DPAPI). The next start of the
     service signs in silently from that cache; the tab opens again only when the cache has expired or was cleared.

Everything here is plain azure-identity; nothing is stored by this project except the account record file.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from .config import LlmSettings

log = logging.getLogger("agents.entra")


class _Silent:
    """Wraps the browser credential so it never opens a tab on its own: sign-in happens in `ensure_signed_in` only."""


def _load_record(path: str):
    from azure.identity import AuthenticationRecord

    p = Path(path)
    if not p.is_file():
        return None
    try:
        return AuthenticationRecord.deserialize(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001  a damaged record only means one more browser sign-in
        return None


def _save_record(path: str, record) -> None:
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(record.serialize(), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        log.warning("could not save the sign-in record: %s", e)


def _persistent_options():
    from azure.identity import TokenCachePersistenceOptions

    try:
        return TokenCachePersistenceOptions(name="coe4-committee-report-assistant")
    except Exception:  # noqa: BLE001
        return None


def build_credential(s: LlmSettings):
    """Return an azure-identity credential (object with get_token) for the settings. Signs in once, here, so callers can share it."""
    from azure.identity import ChainedTokenCredential, DefaultAzureCredential, InteractiveBrowserCredential

    scope = s.scope
    kw = {"interactive_browser_tenant_id": s.tenant_id, "shared_cache_tenant_id": s.tenant_id, "visual_studio_code_tenant_id": s.tenant_id} if s.tenant_id else {}
    machine = DefaultAzureCredential(exclude_interactive_browser_credential=True, **kw)
    try:
        machine.get_token(scope)
        log.info("signed in with an identity found on this machine")
        return machine
    except Exception as e:  # noqa: BLE001  CredentialUnavailable: nothing found; any other error: fall through to the browser too
        log.info("no machine identity (%s)", e.__class__.__name__)
    if not s.entra_browser:
        raise RuntimeError("No Azure sign-in found (run `az login`) and the browser sign-in is switched off (AZURE_ENTRA_BROWSER=false).")

    record = _load_record(s.auth_record) if s.auth_record else None
    base_kw = {"tenant_id": s.tenant_id} if s.tenant_id else {}

    def browser_credential(cached: bool):
        kw = dict(base_kw)
        if cached:
            cache = _persistent_options()
            if cache is not None:
                kw["cache_persistence_options"] = cache
            if record is not None:
                kw["authentication_record"] = record
        return InteractiveBrowserCredential(disable_automatic_authentication=True, **kw)

    browser = browser_credential(cached=True)
    if record is not None:
        try:
            browser.get_token(scope)  # silent: from the protected cache
            log.info("signed in silently with the remembered account")
            return ChainedTokenCredential(browser)
        except Exception as e:  # noqa: BLE001  expired or cleared: sign in again below
            log.info("remembered sign-in no longer valid (%s); opening the browser", e.__class__.__name__)
            browser = browser_credential(cached=True)
    try:
        new_record = browser.authenticate(scopes=[scope])  # opens the browser tab; the user picks the account and signs in
    except Exception as e:  # noqa: BLE001
        if "cache" not in str(e).lower():
            raise
        # No protected cache on this machine (for example Linux without a keyring): sign in without remembering the tokens.
        log.warning("the protected token cache is not available (%s); signing in without remembering it", e.__class__.__name__)
        browser = browser_credential(cached=False)
        new_record = browser.authenticate(scopes=[scope])
        return ChainedTokenCredential(browser)
    if s.auth_record and new_record is not None:
        _save_record(s.auth_record, new_record)
    return ChainedTokenCredential(browser)
