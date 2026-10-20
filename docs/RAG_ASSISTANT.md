# RAG local de l'Assistant ERP

## Fonctionnement
- Sans clé API ni modèle externe : recherche plein texte PostgreSQL (`simple`) sur les fragments de documents.
- Les fragments sont stockés dans `assistant_document_chunk` dans la base de chaque entreprise : les recherches ne traversent jamais les bases des autres entreprises.
- Chaque fragment porte un `module`. Avant d'afficher un résultat, l'API vérifie la permission RBAC `consulter` sur ce module. Les comptes externes ne reçoivent pas les fragments.
- L'API `/api/assistant/chat` retourne `sources` avec titre, origine, module et extrait. `AssistantIA.jsx` les affiche sous la réponse.
- La réponse RAG cite les passages retrouvés; ce n'est pas une génération par LLM. Si aucun passage autorisé ne correspond, l'assistant conserve son comportement habituel.

## Installation
1. Exécuter `backend/database/tenant-template/013_assistant_rag.sql` dans chaque base entreprise déjà créée.
2. Pour importer un document, le découper en fragments de taille raisonnable (par exemple 500 à 1 000 caractères avec un léger chevauchement), puis insérer chaque fragment dans `assistant_document_chunk`.
3. La colonne `module` doit être un module déjà géré par les permissions ERP (`ventes`, `achats`, `clients`, `fournisseurs`, `stock`, `facturation`, `comptabilite`, etc.). Pour documents généraux, configurer aussi le module et la permission `documents.consulter` dans le système RBAC avant de les utiliser.
4. Redémarrer le backend et le frontend après migration.

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
Cette première version est un RAG sans embeddings : elle utilise la recherche lexicale PostgreSQL et peut manquer les synonymes. L'ingestion automatique PDF/DOCX/OCR et la découpe des documents sont une prochaine étape distincte.
