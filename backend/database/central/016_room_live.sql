-- Room Live : persistance des salles, participants, invitations, messages et enregistrements.
-- Script idempotent (CREATE ... IF NOT EXISTS) : peut être rejoué sans risque ni perte de données.
-- Le même fichier est appliqué à la base centrale (compte Super Admin, sans base entreprise)
-- sous le nom central/016_room_live.sql.

CREATE TABLE IF NOT EXISTS room_live_salle (
    id                  VARCHAR(32)  PRIMARY KEY,
    nom                 VARCHAR(100) NOT NULL,
    description         VARCHAR(500) NOT NULL DEFAULT '',
    privee              BOOLEAN      NOT NULL DEFAULT TRUE,
    proprietaire_id     VARCHAR(64)  NOT NULL,
    proprietaire_email  VARCHAR(254),
    cree_le             TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    fermee_le           TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS room_live_participant (
    salle_id    VARCHAR(32)  NOT NULL REFERENCES room_live_salle(id) ON DELETE CASCADE,
    user_id     VARCHAR(64)  NOT NULL,
    email       VARCHAR(254),
    role        VARCHAR(16)  NOT NULL DEFAULT 'member' CHECK (role IN ('host', 'cohost', 'member', 'observer')),
    rejoint_le  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    bloque      BOOLEAN      NOT NULL DEFAULT FALSE,
    PRIMARY KEY (salle_id, user_id)
);

CREATE TABLE IF NOT EXISTS room_live_invitation (
    salle_id   VARCHAR(32)  NOT NULL REFERENCES room_live_salle(id) ON DELETE CASCADE,
    email      VARCHAR(254) NOT NULL,
    expire_le  TIMESTAMPTZ  NOT NULL,
    PRIMARY KEY (salle_id, email)
);

CREATE TABLE IF NOT EXISTS room_live_message (
    id              VARCHAR(32)  PRIMARY KEY,
    salle_id        VARCHAR(32)  NOT NULL REFERENCES room_live_salle(id) ON DELETE CASCADE,
    expediteur_id   VARCHAR(64)  NOT NULL,
    expediteur      VARCHAR(254),
    contenu         TEXT         NOT NULL,
    cree_le         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_room_live_message_salle ON room_live_message (salle_id, cree_le);

-- Enregistrements audio/vidéo. Le fichier est stocké sur disque (RECORDINGS_DIR) ; seule la
-- métadonnée est en base. Les lignes survivent à la fermeture de la salle (conservation
-- gouvernée par retention_jusqu_au), d'où l'absence de clé étrangère vers la salle.
CREATE TABLE IF NOT EXISTS room_live_enregistrement (
    id                   VARCHAR(32)  PRIMARY KEY,
    salle_id             VARCHAR(32)  NOT NULL,
    salle_nom            VARCHAR(100),
    proprietaire_id      VARCHAR(64)  NOT NULL,
    demarre_par_id       VARCHAR(64)  NOT NULL,
    demarre_par_email    VARCHAR(254),
    demarre_le           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    termine_le           TIMESTAMPTZ,
    statut               VARCHAR(16)  NOT NULL DEFAULT 'en_cours'
                         CHECK (statut IN ('en_cours', 'termine', 'interrompu')),
    mime                 VARCHAR(64)  NOT NULL DEFAULT 'video/webm',
    taille_octets        BIGINT       NOT NULL DEFAULT 0,
    chemin               VARCHAR(255),
    sequence_suivante    INTEGER      NOT NULL DEFAULT 0,
    retention_jusqu_au   TIMESTAMPTZ  NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_room_live_enr_salle ON room_live_enregistrement (salle_id, demarre_le DESC);
CREATE INDEX IF NOT EXISTS idx_room_live_enr_retention ON room_live_enregistrement (retention_jusqu_au);
-- Un seul enregistrement actif par salle (garanti par la base, pas seulement par le code).
CREATE UNIQUE INDEX IF NOT EXISTS ux_room_live_enr_en_cours ON room_live_enregistrement (salle_id) WHERE statut = 'en_cours';

CREATE TABLE IF NOT EXISTS room_live_consentement (
    enregistrement_id  VARCHAR(32) NOT NULL REFERENCES room_live_enregistrement(id) ON DELETE CASCADE,
    user_id            VARCHAR(64) NOT NULL,
    email              VARCHAR(254),
    decision           VARCHAR(8)  NOT NULL CHECK (decision IN ('accepte', 'refuse')),
    decide_le          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (enregistrement_id, user_id)
);

-- Journal d'audit des accès aux enregistrements (démarrage, arrêt, consultation, suppression, purge).
CREATE TABLE IF NOT EXISTS room_live_enregistrement_journal (
    id                 BIGSERIAL    PRIMARY KEY,
    enregistrement_id  VARCHAR(32)  NOT NULL,
    user_id            VARCHAR(64),
    email              VARCHAR(254),
    action             VARCHAR(24)  NOT NULL,
    fait_le            TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_room_live_journal_enr ON room_live_enregistrement_journal (enregistrement_id, fait_le);
