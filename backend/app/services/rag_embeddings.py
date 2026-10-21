
"""Embeddings sémantiques locaux pour le RAG ERP.

Le modèle fonctionne localement dans le conteneur backend.
Aucun texte ni aucune question n'est envoyé à une API d'embeddings.
Au premier lancement, FastEmbed télécharge le modèle dans son cache.
"""
from __future__ import annotations

import logging
import math
import os
from functools import lru_cache
from typing import Iterable

logger = logging.getLogger("erp.rag.embeddings")

MODEL_NAME = os.getenv(
    "RAG_EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)


@lru_cache(maxsize=1)
def _model():
    try:
        from fastembed import TextEmbedding
    except ImportError as exc:
        raise RuntimeError(
            "Le moteur d'embeddings local n'est pas installé. "
            "Installez les dépendances backend."
        ) from exc

    logger.info(
        "Initialisation du modèle d'embeddings local: %s",
        MODEL_NAME,
    )

    return TextEmbedding(
        model_name=MODEL_NAME,
        cache_dir=os.getenv(
            "RAG_EMBEDDING_CACHE",
            "/root/.cache/fastembed",
        ),
    )


def embed_texts(
    texts: Iterable[str],
    *,
    query: bool = False,
) -> list[list[float]]:
    """Calcule localement les embeddings des documents ou des questions."""
    values = [str(text or "").strip() for text in texts]
    values = [text for text in values if text]

    if not values:
        return []

    # Ce modèle multilingue ne nécessite pas les préfixes E5.
    try:
        vectors = _model().embed(values)
        return [
            [float(value) for value in vector]
            for vector in vectors
        ]
    except Exception as exc:
        logger.exception("Échec de calcul des embeddings locaux")
        raise RuntimeError(
            "Le modèle RAG local n'est pas disponible. "
            "Vérifiez son téléchargement, le cache et la connexion réseau."
        ) from exc


def cosine_similarity(
    left: list[float] | None,
    right: list[float] | None,
) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    dot = sum(a * b for a, b in zip(left, right))
    norm_left = math.sqrt(sum(a * a for a in left))
    norm_right = math.sqrt(sum(b * b for b in right))

    if not norm_left or not norm_right:
        return 0.0

    return dot / (norm_left * norm_right)
