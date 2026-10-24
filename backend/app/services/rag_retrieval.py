"""Helpers déterministes pour le reranking hybride des résultats RAG."""
from __future__ import annotations
import re
import unicodedata

STOP_WORDS = {
    "quel", "quelle", "quels", "quelles", "comment", "pourquoi",
    "est", "sont", "les", "des", "une", "un", "dans", "pour",
    "avec", "sur", "par", "que", "qui", "quoi", "the", "what",
    "which", "where", "when", "does", "this", "that", "from",
    "and", "for", "are", "was", "der", "die", "und",
}

def normaliser_termes(value: str | None) -> set[str]:
    value = (value or "").lower().replace("’", "'")
    value = "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))
    return set(re.findall(r"[\w-]{2,}", value, flags=re.UNICODE))

def score_hybride(question: str, contenu: str, score_semantique: float) -> tuple[float, float]:
    question_terms = normaliser_termes(question) - STOP_WORDS
    contenu_terms = normaliser_termes(contenu)
    recouvrement = len(question_terms & contenu_terms) / max(1, len(question_terms))
    return (0.78 * score_semantique) + (0.22 * recouvrement), recouvrement

def passage_pertinent(score_semantique: float, score_lexical: float) -> bool:
    return score_semantique >= 0.42 or (score_lexical >= 0.5 and score_semantique >= 0.28)
