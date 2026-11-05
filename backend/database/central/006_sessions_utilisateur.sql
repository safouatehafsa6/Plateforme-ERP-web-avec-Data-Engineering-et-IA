-- 006_sessions_utilisateur.sql
-- Migration a executer sur la BASE CENTRALE.
--
-- Une ligne = une connexion (un jeton JWT emis). Le jeton porte le "jti"
-- (identifiant de session) ; a chaque requete le backend verifie ici que
-- la session n'est ni revoquee ni expiree. Sans cette table, un jeton
-- reste valable jusqu'a son expiration (8 h) meme apres deconnexion.

CREATE TABLE IF NOT EXISTS session_utilisateur (
    jti               VARCHAR(64)  PRIMARY KEY,
    type_compte       VARCHAR(20)  NOT NULL,      -- plateforme, interne, externe
    utilisateur_id    VARCHAR(64)  NOT NULL,
    email             VARCHAR(255) NOT NULL,
    entreprise_id     VARCHAR(64),                -- NULL pour le super admin
    nom_base          VARCHAR(100),
    systeme           VARCHAR(50),
    navigateur        VARCHAR(50),
    appareil          VARCHAR(20),                -- ordinateur, mobile
    adresse_ip        VARCHAR(45),
    user_agent        TEXT,
    cree_le           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    derniere_activite TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    expire_le         TIMESTAMPTZ  NOT NULL,
    revoquee_le       TIMESTAMPTZ,
    motif_revocation  VARCHAR(50)
    -- motifs : deconnexion, revoquee_par_utilisateur, revoquee_par_admin,
    --          mot_de_passe_reinitialise
);

CREATE INDEX IF NOT EXISTS idx_session_utilisateur_compte
    ON session_utilisateur (type_compte, utilisateur_id);

CREATE INDEX IF NOT EXISTS idx_session_utilisateur_entreprise
    ON session_utilisateur (entreprise_id);

CREATE INDEX IF NOT EXISTS idx_session_utilisateur_email
    ON session_utilisateur (email);
