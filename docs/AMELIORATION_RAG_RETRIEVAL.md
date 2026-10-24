# Amélioration du retrieval RAG

## Changements
- Recherche hybride : similarité sémantique locale et recouvrement lexical.
- Classement par score combiné, avec seuils de pertinence pour éviter de retourner automatiquement des passages faibles.
- Extraits de sources limités à 280 caractères pour le contexte et l’interface.
- Réponse de repli extractive limitée à une seule phrase (220 caractères maximum), avec titre et référence de la source.
- Prompt LLM renforcé : 1 à 3 phrases, idéalement moins de 80 mots, citation du document et abstention explicite si les sources ne répondent pas.
- Prompt de génération renforcé : réponse directe, contexte uniquement, distinction entre codes/valeurs, pas de copie intégrale du document, source citée.
- Tests unitaires du score lexical, de la normalisation et du filtre de pertinence.

## Paramètres à valider sur les documents réels
Les seuils actuels (`0.42` sémantique, ou `0.28` sémantique avec `0.50` de recouvrement lexical) sont des valeurs initiales à évaluer avec un jeu de questions réel. Ils ne garantissent pas à eux seuls la pertinence de toutes les réponses.

## Tests
Depuis le dossier `backend`, exécuter :

```bash
pytest -q tests/test_rag_retrieval.py tests/test_rag_embeddings.py
python -m compileall -q app/routers/assistant.py app/services/rag_generation.py app/services/rag_retrieval.py app/services/rag_response.py
```

La génération dépend toujours de la configuration existante `RAG_LLM_BASE_URL`, `RAG_LLM_MODEL` et éventuellement `RAG_LLM_API_KEY`. Ne pas mettre de clé secrète dans le dépôt Git.
