# Test du RAG sémantique local

## Fonctionnement ajouté
- Extraction de texte PDF/DOCX et découpage avec chevauchement (déjà présent).
- Calcul des embeddings avec `intfloat/multilingual-e5-small` via FastEmbed dans le backend.
- Génération facultative d'une réponse synthétisée par un endpoint compatible OpenAI (`RAG_LLM_BASE_URL`, `RAG_LLM_MODEL`, `RAG_LLM_API_KEY`). Si aucun endpoint n'est configuré, le chat affiche les extraits retrouvés avec les sources.
- Stockage des vecteurs dans PostgreSQL (JSONB) par base entreprise.
- Recherche par similarité cosinus locale et retour des sources dans le chat.
- Les anciens chunks sans vecteur sont réindexés à la première recherche, par lots de 2 000 maximum.

## Activer la génération de réponses (facultatif)
Dans le `.env` local, renseignez `RAG_LLM_BASE_URL`, `RAG_LLM_MODEL` et, si le fournisseur le demande, `RAG_LLM_API_KEY`. L'endpoint doit exposer `/chat/completions` compatible OpenAI. Sans configuration, la recherche sémantique locale fonctionne et le chat présente les extraits retrouvés.

## Première exécution
Le modèle doit être présent dans le cache FastEmbed. Au premier démarrage, FastEmbed peut le télécharger une fois. Le cache est conservé dans le volume Docker `rag_model_cache`. Ensuite, les calculs et la recherche se font localement dans le conteneur backend. Aucune API d'embeddings externe n'est utilisée.

Rebuild du backend depuis la racine du projet :

```powershell
docker compose build backend
docker compose up -d backend
docker compose logs -f backend
```

Si votre service Compose s'appelle `erp-backend` et non `backend`, gardez le nom défini dans votre fichier compose.

## Démonstration manuelle
1. Connectez-vous avec un compte interne qui a la permission `documents.creer`.
2. Ouvrez la gestion des documents et importez un PDF ou DOCX avec du texte sélectionnable.
3. Attendez le message `Document importé`.
4. Dans l'assistant, posez une question avec des mots différents de ceux du document, mais qui exprime la même idée.
5. Vérifiez que la réponse cite le document dans la section **Sources** et que l'extrait correspond à la question.
6. Posez une question dont la réponse n'existe dans aucun document : le système ne doit pas afficher de source non pertinente.
7. Vérifiez les journaux backend en cas de problème : `docker compose logs --tail=200 backend`.

## Limites actuelles
- PDF scannés sans couche texte : OCR non pris en charge.
- Les vecteurs sont comparés en mémoire côté backend; pour de très grands corpus, il faudra migrer vers pgvector ou une base vectorielle locale.
- Le modèle d'embeddings se télécharge au premier démarrage s'il n'est pas déjà en cache. Le texte et les vecteurs restent dans l'infrastructure de l'application.
