-- Demandes d'assistance (support) créées depuis le bouton flottant « Assistance / Contact ».
-- Chaque demande appartient à un compte précis (type_compte + utilisateur_id).
CREATE TABLE IF NOT EXISTS demande_support (
    id             SERIAL PRIMARY KEY,
    type_compte    VARCHAR(30)  NOT NULL DEFAULT 'interne',
    utilisateur_id VARCHAR(120) NOT NULL,
    auteur         VARCHAR(200),
    sujet          VARCHAR(150) NOT NULL,
    description    TEXT NOT NULL,
    page           VARCHAR(300),
    statut         VARCHAR(20)  NOT NULL DEFAULT 'ouverte',
    capture_type   VARCHAR(30),
    capture        BYTEA,
    cree_le        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    mis_a_jour_le  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT demande_support_statut_chk CHECK (statut IN ('ouverte', 'en_cours', 'resolue'))
);
CREATE INDEX IF NOT EXISTS idx_demande_support_auteur
    ON demande_support (type_compte, utilisateur_id, cree_le DESC);
CREATE INDEX IF NOT EXISTS idx_demande_support_statut
    ON demande_support (statut, cree_le DESC);
