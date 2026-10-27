-- Moteur de calcul métier centralisé (calculs basés sur une période et un taux).
--   bareme_taux   : référentiels de taux (un barème « Taux de référence » est créé par défaut)
--   periode_taux  : périodes + taux d'un barème (administrées par les administrateurs)
--   calcul_taux   : historique complet de tous les calculs (détail figé au moment du calcul)
-- Idempotent : peut être exécuté plusieurs fois (le backend l'applique aussi automatiquement
-- à la première utilisation sur une base existante).

CREATE TABLE IF NOT EXISTS bareme_taux (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(40)  UNIQUE NOT NULL,
    libelle     VARCHAR(150) NOT NULL,
    description TEXT,
    actif       BOOLEAN NOT NULL DEFAULT TRUE,
    cree_le     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS periode_taux (
    id          SERIAL PRIMARY KEY,
    bareme_id   INTEGER NOT NULL REFERENCES bareme_taux(id) ON DELETE CASCADE,
    date_debut  DATE NOT NULL,
    date_fin    DATE NOT NULL,
    taux        NUMERIC(7,4) NOT NULL,
    actif       BOOLEAN NOT NULL DEFAULT TRUE,
    cree_par    VARCHAR(200),
    cree_le     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    modifie_par VARCHAR(200),
    modifie_le  TIMESTAMPTZ,
    CONSTRAINT periode_taux_dates_chk CHECK (date_fin >= date_debut),
    CONSTRAINT periode_taux_taux_chk  CHECK (taux >= 0 AND taux <= 100)
);
CREATE INDEX IF NOT EXISTS idx_periode_taux_bareme ON periode_taux (bareme_id, date_debut);

CREATE SEQUENCE IF NOT EXISTS calcul_taux_seq;

CREATE TABLE IF NOT EXISTS calcul_taux (
    id                   SERIAL PRIMARY KEY,
    reference            VARCHAR(30) UNIQUE NOT NULL,
    mode                 VARCHAR(20) NOT NULL,
    module_source        VARCHAR(40) NOT NULL DEFAULT 'general',
    libelle              VARCHAR(200),
    montant              NUMERIC(18,2) NOT NULL,
    date_debut           DATE NOT NULL,
    date_fin             DATE NOT NULL,
    taux                 NUMERIC(7,4),
    bareme_id            INTEGER REFERENCES bareme_taux(id) ON DELETE SET NULL,
    bareme_libelle       VARCHAR(150),
    base_jours           INTEGER NOT NULL DEFAULT 365,
    inclure_dernier_jour BOOLEAN NOT NULL DEFAULT FALSE,
    devise               VARCHAR(10) NOT NULL DEFAULT 'MAD',
    nombre_jours         INTEGER NOT NULL,
    resultat             NUMERIC(18,2) NOT NULL,
    details              JSONB NOT NULL DEFAULT '[]'::jsonb,
    cree_par             VARCHAR(120) NOT NULL,
    cree_par_nom         VARCHAR(200),
    cree_le              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    modifie_par          VARCHAR(200),
    modifie_le           TIMESTAMPTZ,
    CONSTRAINT calcul_taux_mode_chk CHECK (mode IN ('taux_unique', 'taux_variable')),
    CONSTRAINT calcul_taux_dates_chk CHECK (date_fin >= date_debut)
);
CREATE INDEX IF NOT EXISTS idx_calcul_taux_recent ON calcul_taux (cree_le DESC);
CREATE INDEX IF NOT EXISTS idx_calcul_taux_mode ON calcul_taux (mode, cree_le DESC);

-- Barème par défaut.
INSERT INTO bareme_taux (code, libelle, description)
SELECT 'TAUX_REFERENCE', 'Taux de référence', 'Périodes et taux fixes utilisés par défaut pour les calculs à taux variables.'
WHERE NOT EXISTS (SELECT 1 FROM bareme_taux WHERE code = 'TAUX_REFERENCE');

-- Nouveau module de permissions : « calculs » (6 actions, comme les autres modules).
INSERT INTO permission (module, action)
SELECT 'calculs', a.action
FROM (VALUES ('consulter'), ('creer'), ('modifier'), ('supprimer'), ('valider'), ('exporter')) AS a(action)
WHERE NOT EXISTS (SELECT 1 FROM permission p WHERE p.module = 'calculs' AND p.action = a.action);

-- Profil financier : consulter, créer, modifier et exporter les calculs (modifiable ensuite).
INSERT INTO role_permission (role_id, permission_id)
SELECT r.id, p.id
FROM role r
JOIN permission p ON p.module = 'calculs' AND p.action IN ('consulter', 'creer', 'modifier', 'exporter')
WHERE r.nom = 'Responsable Financier et Comptable'
  AND NOT EXISTS (SELECT 1 FROM role_permission rp WHERE rp.role_id = r.id AND rp.permission_id = p.id);

-- Le rôle Admin reçoit toutes les permissions du module.
INSERT INTO role_permission (role_id, permission_id)
SELECT r.id, p.id
FROM role r
JOIN permission p ON p.module = 'calculs'
WHERE r.nom = 'Admin'
  AND NOT EXISTS (SELECT 1 FROM role_permission rp WHERE rp.role_id = r.id AND rp.permission_id = p.id);
