-- Notifications isolées par type de compte, utilisateur et entreprise.
CREATE TABLE IF NOT EXISTS notification_utilisateur (
    id BIGSERIAL PRIMARY KEY,
    type_compte VARCHAR(30) NOT NULL,
    utilisateur_id VARCHAR(120) NOT NULL,
    entreprise_id INTEGER REFERENCES entreprise(id) ON DELETE CASCADE,
    titre VARCHAR(180) NOT NULL,
    message VARCHAR(2000) NOT NULL,
    lien VARCHAR(500),
    categorie VARCHAR(20) NOT NULL DEFAULT 'info'
        CHECK (categorie IN ('info', 'success', 'warning', 'error')),
    cree_le TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lue_le TIMESTAMPTZ,
    CONSTRAINT notification_lien_interne CHECK (lien IS NULL OR (lien LIKE '/%' AND lien NOT LIKE '//%'))
);

CREATE INDEX IF NOT EXISTS idx_notification_utilisateur_non_lues
    ON notification_utilisateur (type_compte, utilisateur_id, entreprise_id, cree_le DESC)
    WHERE lue_le IS NULL;
CREATE INDEX IF NOT EXISTS idx_notification_utilisateur_liste
    ON notification_utilisateur (type_compte, utilisateur_id, entreprise_id, cree_le DESC, id DESC);
