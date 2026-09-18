-- 004_index_comptes_entreprise.sql
-- Migration à exécuter sur la BASE CENTRALE.
--
-- Nécessaire pour le "point d'entrée unique" de connexion décrit par
-- l'entreprise : "le système identifie automatiquement le type
-- d'utilisateur dès la saisie de ses identifiants et le redirige vers
-- l'interface qui lui est dédiée, sans aucune manipulation
-- supplémentaire."
--
-- Les comptes Administrateur/Collaborateur vivent uniquement dans la
-- base de leur entreprise (isolation multi-tenant) : la base centrale ne
-- connaît donc pas leur mot de passe, seulement la correspondance
-- email -> entreprise, pour savoir dans quelle base chercher au moment
-- de la connexion.

CREATE TABLE IF NOT EXISTS compte_index (
    email           VARCHAR(150) PRIMARY KEY,
    entreprise_id   INTEGER NOT NULL REFERENCES entreprise(id) ON DELETE CASCADE,
    nom_base        VARCHAR(100) NOT NULL,
    date_indexation TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_compte_index_entreprise ON compte_index(entreprise_id);
