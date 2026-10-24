"""Réponses de repli pour le RAG documentaire (utilisées quand aucun LLM n'est disponible).
Elles listent les meilleurs extraits trouvés avec leurs sources et le disent explicitement :
ce n'est pas une synthèse."""
import re

MAX_SOURCES = 3
MAX_CHARS = 200

_TEXTS = {
    "fr": ("Extrait trouvé", "Extraits trouvés", "Source", "synthèse IA indisponible"),
    "en": ("Excerpt found", "Excerpts found", "Source", "AI summary unavailable"),
    "ar": ("مقتطف ذو صلة", "مقتطفات ذات صلة", "المصدر", "الملخص الذكي غير متوفر"),
}


def _phrase(source):
    extrait = " ".join((source.get("excerpt") or "").split())
    phrases = re.split(r"(?<=[.!?。؟])\s+", extrait)
    phrase = next((p.strip() for p in phrases if p.strip()), extrait)
    if len(phrase) > MAX_CHARS:
        phrase = phrase[:MAX_CHARS].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return phrase


def reponse_rag_concise(sources, langue):
    """Liste jusqu'à 3 extraits courts avec leur source ; précise que ce n'est pas une synthèse."""
    if not sources:
        return None
    un, plusieurs, label_source, note = _TEXTS.get(langue, _TEXTS["fr"])
    retenues = sources[:MAX_SOURCES]
    lignes = []
    for i, source in enumerate(retenues, 1):
        titre = source.get("title") or "Document sans titre"
        reference = source.get("source") or titre
        prefixe = f"{i}. " if len(retenues) > 1 else ""
        lignes.append(f"{prefixe}{_phrase(source)}\n   {label_source} : {titre} ({reference})" if len(retenues) > 1
                      else f"{_phrase(source)}\n{label_source} : {titre} ({reference})")
    entete = f"{un if len(retenues) == 1 else plusieurs} ({note}) :"
    return entete + "\n" + "\n".join(lignes)
