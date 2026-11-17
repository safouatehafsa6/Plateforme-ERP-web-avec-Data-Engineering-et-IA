# Amélioration IDP — Import des classeurs ODS

**Projet :** Plateforme ERP Web avec Data Engineering et Intelligence Artificielle  
**Périmètre :** importation intelligente de documents (IDP)  
**Livraison :** prise en charge des tableurs OpenDocument (`.ods`)

## 1. Constat initial

La page « Documents intelligents (IDP) » était déjà présente dans le projet. Elle permettait notamment de déposer un document, d'extraire des informations, de corriger les champs, de valider le document et, pour les documents éligibles, de proposer une intégration dans Achats.

Le lecteur IDP reconnaissait déjà plusieurs formats, mais ne reconnaissait pas les classeurs ODS. Ce format figure dans le périmètre d'importation demandé pour le projet.

## 2. Travail réalisé

- Détection du format ODS à partir du type MIME interne du fichier, et non de sa seule extension.
- Lecture des feuilles et des cellules du classeur.
- Extraction des valeurs textuelles et des valeurs stockées dans les attributs numériques, dates et booléens.
- Prise en compte des cellules et lignes répétées, avec des limites de traitement.
- Analyse du XML avec `defusedxml` pour refuser les entités et DTD externes.
- Conservation des limites de taille et de décompression déjà appliquées aux archives Office.
- Ajout de `.ods` au sélecteur de fichiers de la page Documents IA.
- Ajout de l'extension ODS à la liste des formats de téléchargement de l'original.
- Aucun nouveau paquet n’est nécessaire à l’exécution : le lecteur s’appuie sur `defusedxml`, déjà présent dans les dépendances du projet.

## 3. Fichiers modifiés

- `backend/app/services/idp_extraction.py`
- `backend/app/routers/idp.py`
- `backend/tests/test_idp.py`
- `frontend/src/pages/Idp.jsx`
- `README.md`
- `LISEZMOI-MISE-A-JOUR.txt`

## 4. Vérifications réalisées

- 4 nouveaux tests ODS : extraction des cellules, détection par MIME, refus d'une archive ZIP non ODS et refus des entités XML externes.
- Suite `tests.test_idp` : **36 tests réussis**.
- Suite `tests.test_idp_integration` : **15 tests réussis** (tests avec dépendances simulées, pas une intégration à une base PostgreSQL réelle).
- Classeur ODS de démonstration généré avec un outil OpenDocument puis lu avec le lecteur IDP : une feuille et 11 lignes extraites.
- Compilation Python des fichiers backend : réussie.

Le build React/Vite et le parcours complet dans le navigateur restent à exécuter dans l'environnement Docker du projet. Le traitement IDP complet dépend également de la disponibilité du fournisseur LLM configuré (Ollama ou autre fournisseur configuré).

## 5. Démonstration

Le fichier `docs/exemple_facture_demo.ods` est un exemple synthétique, sans données réelles. Il peut servir à vérifier que le sélecteur de fichiers accepte ODS et que le lecteur extrait les cellules. Pour démontrer le parcours IA complet (structuration, correction, validation et intégration dans Achats), le service LLM doit être joignable et le document doit être vérifié avant validation.

## 6. Limites

Cette amélioration ajoute le format ODS uniquement. Elle ne signifie pas que tous les formats d'importation et d'exportation demandés sont désormais pris en charge. Les formats non implémentés doivent rester identifiés comme travaux distincts.
