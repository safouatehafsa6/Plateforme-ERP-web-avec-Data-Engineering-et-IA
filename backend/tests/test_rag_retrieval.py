from app.services.rag_retrieval import normaliser_termes, score_hybride, passage_pertinent


def test_normaliser_termes_ignore_accents_and_case():
    assert "siege" in normaliser_termes("SIÈGE social")


def test_lexical_score_prioritizes_exact_terms():
    relevant, overlap_relevant = score_hybride("code validation Atlas", "Code de validation Atlas ORION-472", 0.60)
    unrelated, overlap_unrelated = score_hybride("code validation Atlas", "Adresse du siège social", 0.60)
    assert overlap_relevant > overlap_unrelated
    assert relevant > unrelated


def test_low_relevance_passage_is_rejected():
    assert not passage_pertinent(0.20, 0.10)
    assert passage_pertinent(0.50, 0.10)
    assert passage_pertinent(0.30, 0.60)


def test_rag_fallback_is_short_and_cites_source():
    from app.services.rag_response import reponse_rag_concise

    sources = [{
        "title": "Procédure achats",
        "source": "procedure_achats.pdf (p. 2)",
        "excerpt": "Le délai de validation est de 48 heures. " + ("Texte supplémentaire. " * 40),
    }]
    answer = reponse_rag_concise(sources, "fr")
    assert "48 heures" in answer
    assert "Procédure achats" in answer
    assert "procedure_achats.pdf (p. 2)" in answer
    assert len(answer) < 320
    assert "Texte supplémentaire. Texte supplémentaire. Texte supplémentaire." not in answer


def test_rag_fallback_handles_empty_sources():
    from app.services.rag_response import reponse_rag_concise
    assert reponse_rag_concise([], "fr") is None
