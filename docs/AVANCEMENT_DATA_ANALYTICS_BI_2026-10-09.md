# Rapport d'avancement — Data Engineering et Data Analytics / BI
Date : 9 octobre 2026

## 1. Data Engineering
- Source : PostgreSQL de l'ERP.
- Traitement : Apache Spark 3.5.3.
- Stockage objet : MinIO.
- Formats : Parquet.
- Zones : raw, staging et curated.
- Jeux de données transformés : ventes, factures et achats.
- Les écritures Spark dans MinIO ont été vérifiées par la présence des fichiers Parquet et des marqueurs _SUCCESS.

## 2. Data Analytics / BI
- Metabase installé et accessible sur http://localhost:3001.
- Connexion à la base PostgreSQL de l'ERP testée avec des requêtes SQL.
- Indicateurs créés : commandes, factures, achats, clients et fournisseurs.
- Analyses créées : commandes par statut, évolution mensuelle des commandes et achats par statut.
- Tableau de bord : ERP — Tableau de bord décisionnel.
- Les visualisations graphiques restent à finaliser.

## 3. Orchestration
Un DAG Airflow a été ajouté pour lancer le traitement Spark.
La validation complète de l'exécution orchestrée reste à finaliser.

## 4. Prochaines étapes
- Finaliser les graphiques et la mise en page du tableau de bord.
- Valider l'exécution du pipeline par Airflow.
- Compléter les tests de bout en bout.
- Documenter la chaîne PostgreSQL -> Spark -> MinIO -> BI.

Note : les identifiants et mots de passe ne doivent pas être enregistrés dans ce dépôt.
