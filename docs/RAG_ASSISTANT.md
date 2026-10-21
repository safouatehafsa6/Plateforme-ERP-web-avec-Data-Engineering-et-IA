# RAG local de l'Assistant ERP

## Fonctionnement
- Le texte des PDF/DOCX est extrait puis découpé en fragments avec chevauchement.
- Les embeddings multilingues sont calculés localement dans le backend avec FastEmbed (`intfloat/multilingual-e5-small`). La recherche compare la similarité cosinus des vecteurs; aucun service d'embeddings externe n'est appelé.
- Au premier lancement, le modèle peut être téléchargé une fois et conservé dans le volume Docker `rag_model_cache`; ensuite, calcul et recherche sont locaux.
- Les fragments sont stockés dans `assistant_document_chunk` dans la base de chaque entreprise : les recherches ne traversent jamais les bases des autres entreprises.
- Chaque fragment porte un `module`. Avant d'afficher un résultat, l'API vérifie la permission RBAC `consulter` sur ce module. Les comptes externes ne reçoivent pas les fragments.
- L'API `/api/assistant/chat` retourne `sources` avec titre, origine, module et extrait. `AssistantIA.jsx` les affiche sous la réponse.
- Si `RAG_LLM_BASE_URL` et `RAG_LLM_MODEL` sont configurés, les passages récupérés alimentent une génération de réponse via un endpoint compatible OpenAI. Sans configuration, les extraits et leurs sources sont affichés directement. Si aucun passage autorisé ne correspond, l'assistant conserve son comportement habituel.

## Installation
1. Reconstruire le backend pour installer `fastembed`.
2. Pour les bases entreprise déjà créées, appliquer les migrations `013_assistant_rag.sql`, `014_assistant_documents.sql`, `015_documents_permissions.sql` et `016_assistant_rag_embeddings.sql` dans cet ordre. Le code tente aussi d'ajouter les colonnes d'embedding de façon idempotente lors d'une requête/import.
3. Importer les documents via le trombone dans l'assistant. Les fragments et leurs vecteurs sont enregistrés automatiquement.
4. Poser une question au sujet du contenu. Les sources apparaissent sous la réponse; il ne faut pas réimporter le même fichier à chaque question.

## Exemple d'insertion
```sql
INSERT INTO assistant_document_chunk
(document_id, titre, source, module, contenu, langue)
VALUES
('guide-ventes-001', 'Guide de gestion des ventes', 'guide_ventes.pdf', 'ventes',
 'Les commandes confirmées peuvent être consultées depuis le module Ventes.', 'fr');
```

## Test manuel
- Se connecter avec un compte interne autorisé au module `ventes`.
- Poser une question reprenant des termes présents dans le fragment.
- Vérifier que la réponse contient le passage et que les Sources affichent le titre, le fichier et l'extrait.
- Refaire le test avec un utilisateur sans permission `ventes.consulter` : le fragment ne doit pas apparaître.
- Vérifier dans une seconde base entreprise que le fragment de la première entreprise n'est jamais retourné.

## Limites
Le classement sémantique est local. La génération par LLM est facultative et configurable via un endpoint compatible OpenAI. Pour les très grands corpus, remplacer la comparaison en mémoire par pgvector ou un moteur vectoriel local. L'OCR des PDF scannés n'est pas pris en charge.
