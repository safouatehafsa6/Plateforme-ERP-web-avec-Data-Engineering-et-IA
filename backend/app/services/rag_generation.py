"""Génération facultative d'une réponse RAG via une API compatible OpenAI.
La recherche et les embeddings restent locaux. Sans endpoint configuré, le système
retourne les passages retrouvés, sans prétendre les avoir synthétisés par un LLM.
"""
import logging
import os

import httpx

logger = logging.getLogger("erp.rag.generation")


def generer_reponse(question: str, sources: list[dict], langue: str) -> str | None:
    base_url = os.getenv("RAG_LLM_BASE_URL", "").strip().rstrip("/")
    model = os.getenv("RAG_LLM_MODEL", "").strip()
    api_key = os.getenv("RAG_LLM_API_KEY", "").strip()
    if not base_url or not model or not sources:
        return None

    langue_nom = {"fr": "français", "en": "English", "ar": "العربية"}.get(langue, "français")
    context = "\n\n".join(
        f"Source: {item.get('title')} — {item.get('source')}\nExtrait: {item.get('excerpt')}"
        for item in sources
    )
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": (
                "Tu es l'assistant documentaire d'un ERP. Réponds en " + langue_nom + ". "
                "Utilise uniquement le contexte fourni. Si le contexte ne répond pas à la question, "
                "dis clairement que les documents disponibles ne permettent pas de répondre. "
                "Ne crée aucun fait. Mentionne les titres des sources pertinentes."
            )},
            {"role": "user", "content": f"Question: {question}\n\nContexte documentaire:\n{context}"},
        ],
    }
    try:
        with httpx.Client(timeout=35.0) as client:
            response = client.post(base_url + "/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            answer = data["choices"][0]["message"]["content"]
            return answer.strip() if isinstance(answer, str) and answer.strip() else None
    except Exception:
        logger.exception("La génération RAG via le modèle configuré a échoué; les extraits seront affichés")
        return None
