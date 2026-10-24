"""Client LLM unique (API compatible OpenAI) : Ollama local par défaut, OpenAI en option.

Choix du fournisseur via LLM_PROVIDER :
  - ollama (défaut) : modèle open source local, aucune clé API requise
  - openai          : API OpenAI (nécessite RAG_LLM_API_KEY et un crédit valide)
  - none            : aucun LLM, le RAG affiche uniquement les extraits trouvés
RAG_LLM_BASE_URL / RAG_LLM_MODEL / RAG_LLM_API_KEY, si renseignées, restent prioritaires
(compatibilité avec la configuration existante).

Sécurité : la clé API et le corps des réponses d'erreur ne sont jamais journalisés
(un 401 OpenAI peut contenir un fragment de la clé).
"""
from __future__ import annotations

import logging
import os
import time

import httpx

logger = logging.getLogger("erp.llm")

DEFAULTS = {
    "ollama": {"base_url": "http://host.docker.internal:11434/v1", "model": "qwen2.5:3b", "timeout": 120.0},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini", "timeout": 35.0},
}

# Après une erreur « durable » (clé invalide, crédit épuisé, serveur injoignable),
# on évite de ré-appeler le fournisseur à chaque message pendant ce délai.
COOLDOWN_SECONDS = float(os.getenv("RAG_LLM_COOLDOWN", "120"))
_blocked_until: dict[str, float] = {}


class LLMError(Exception):
    """Erreur LLM classée. `kind` : auth, quota, rate_limit, timeout, unreachable,
    model_missing, http, bad_response."""

    def __init__(self, kind: str, status: int | None = None):
        super().__init__(f"{kind}" + (f" (HTTP {status})" if status else ""))
        self.kind = kind
        self.status = status


def get_config() -> dict | None:
    """Retourne la configuration active, ou None si aucun LLM n'est configuré."""
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    base_url = os.getenv("RAG_LLM_BASE_URL", "").strip().rstrip("/")
    model = os.getenv("RAG_LLM_MODEL", "").strip()
    api_key = os.getenv("RAG_LLM_API_KEY", "").strip()

    if provider == "none":
        return None
    if not provider:
        # Rétro-compatibilité : l'ancienne config RAG_LLM_* implique un endpoint explicite.
        provider = "openai" if "openai.com" in base_url else ("ollama" if not base_url else "custom")
    defaults = DEFAULTS.get(provider, {"base_url": "", "model": "", "timeout": 35.0})
    base_url = base_url or defaults["base_url"]
    model = model or defaults["model"]
    if not base_url or not model:
        return None
    if provider == "openai" and not api_key:
        return None  # OpenAI sans clé : inutile d'appeler
    try:
        timeout = float(os.getenv("RAG_LLM_TIMEOUT", "") or defaults["timeout"])
    except ValueError:
        timeout = defaults["timeout"]
    return {"provider": provider, "base_url": base_url, "model": model, "api_key": api_key, "timeout": timeout}


def _classify(response: httpx.Response) -> LLMError:
    status = response.status_code
    if status in (401, 403):
        return LLMError("auth", status)
    if status == 404:
        return LLMError("model_missing", status)
    if status == 429:
        code = ""
        try:
            err = response.json().get("error", {})
            code = str(err.get("code") or err.get("type") or "")
        except Exception:
            pass
        return LLMError("quota" if "quota" in code else "rate_limit", status)
    return LLMError("http", status)


def chat_completion(messages: list[dict], *, temperature: float = 0.1, extra: dict | None = None) -> str:
    """Appelle /chat/completions. Lève LLMError (jamais d'exception brute, jamais de secret)."""
    cfg = get_config()
    if cfg is None:
        raise LLMError("unconfigured")
    key = cfg["provider"] + "|" + cfg["base_url"]
    if _blocked_until.get(key, 0) > time.monotonic():
        raise LLMError("cooldown")

    headers = {"Content-Type": "application/json"}
    if cfg["api_key"]:
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    payload = {"model": cfg["model"], "temperature": temperature, "messages": messages, **(extra or {})}

    try:
        response = httpx.post(cfg["base_url"] + "/chat/completions", headers=headers, json=payload, timeout=cfg["timeout"])
    except httpx.TimeoutException:
        err = LLMError("timeout")
    except httpx.TransportError:
        err = LLMError("unreachable")
    else:
        if response.status_code >= 400:
            err = _classify(response)
        else:
            try:
                answer = response.json()["choices"][0]["message"]["content"]
            except Exception:
                raise LLMError("bad_response", response.status_code) from None
            if not isinstance(answer, str) or not answer.strip():
                raise LLMError("bad_response", response.status_code)
            return answer.strip()

    logger.warning("Appel LLM échoué : provider=%s model=%s erreur=%s", cfg["provider"], cfg["model"], err)
    if err.kind in {"auth", "quota", "unreachable", "model_missing"}:
        _blocked_until[key] = time.monotonic() + COOLDOWN_SECONDS
    raise err


def reset_cooldown() -> None:
    _blocked_until.clear()
