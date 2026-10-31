-- 011_appareils.sql
-- Migration a executer sur la BASE CENTRALE (aussi appliquee automatiquement,
-- et sans risque, au demarrage du backend : tout est idempotent).
--
-- Une ligne = un appareil connu d'un compte (navigateur identifie par un
-- identifiant aleatoire genere par l'interface ; seule son empreinte SHA-256
-- est stockee). Statuts : autorise, bloque, en_attente.

CREATE TABLE IF NOT EXISTS appareil (
    id                 SERIAL PRIMARY KEY,
    type_compte        VARCHAR(20)  NOT NULL,      -- plateforme, interne, externe
    utilisateur_id     VARCHAR(64)  NOT NULL,
    entreprise_id      VARCHAR(64),                -- NULL pour le super admin
    email              VARCHAR(255) NOT NULL,
    empreinte          VARCHAR(64)  NOT NULL,
    nom                VARCHAR(120),
    systeme            VARCHAR(60),
    navigateur         VARCHAR(60),
    type_appareil      VARCHAR(20),
    derniere_ip        VARCHAR(45),
    statut             VARCHAR(20)  NOT NULL DEFAULT 'autorise'
                       CHECK (statut IN ('autorise', 'bloque', 'en_attente')),
    premiere_vue       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    derniere_vue       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    statut_modifie_le  TIMESTAMPTZ,
    statut_modifie_par VARCHAR(255)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_appareil_identite
    ON appareil (type_compte, utilisateur_id, COALESCE(entreprise_id, ''), empreinte);

CREATE INDEX IF NOT EXISTS idx_appareil_entreprise ON appareil (entreprise_id);

ALTER TABLE session_utilisateur ADD COLUMN IF NOT EXISTS appareil_id INTEGER;
CREATE INDEX IF NOT EXISTS idx_session_appareil ON session_utilisateur (appareil_id);
