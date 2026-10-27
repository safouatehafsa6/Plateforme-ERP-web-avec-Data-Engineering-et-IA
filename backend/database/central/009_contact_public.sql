-- Messages envoyés depuis la page publique « Contact » (visiteurs non connectés).
CREATE TABLE IF NOT EXISTS contact_public (
    id        BIGSERIAL PRIMARY KEY,
    nom       VARCHAR(150) NOT NULL,
    email     VARCHAR(200) NOT NULL,
    message   VARCHAR(3000) NOT NULL,
    ip        VARCHAR(64),
    traite    BOOLEAN NOT NULL DEFAULT FALSE,
    cree_le   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_contact_public_recent ON contact_public (traite, cree_le DESC);
