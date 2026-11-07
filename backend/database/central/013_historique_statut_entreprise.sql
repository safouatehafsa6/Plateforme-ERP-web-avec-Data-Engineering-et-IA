CREATE TABLE IF NOT EXISTS historique_statut_entreprise (
    id             BIGSERIAL PRIMARY KEY,
    entreprise_id  INTEGER NOT NULL REFERENCES entreprise(id) ON DELETE CASCADE,
    ancien_statut  VARCHAR(20),
    nouveau_statut VARCHAR(20) NOT NULL,
    acteur         VARCHAR(150),
    motif          TEXT,
    cree_le        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_hist_statut_entreprise
    ON historique_statut_entreprise (entreprise_id, cree_le DESC);

CREATE OR REPLACE FUNCTION trg_historique_statut_entreprise() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO historique_statut_entreprise (entreprise_id, ancien_statut, nouveau_statut, acteur, motif)
        VALUES (NEW.id, NULL, NEW.statut,
                NULLIF(current_setting('app.acteur', true), ''),
                COALESCE(NULLIF(current_setting('app.motif', true), ''), 'creation'));
    ELSIF NEW.statut IS DISTINCT FROM OLD.statut THEN
        INSERT INTO historique_statut_entreprise (entreprise_id, ancien_statut, nouveau_statut, acteur, motif)
        VALUES (NEW.id, OLD.statut, NEW.statut,
                NULLIF(current_setting('app.acteur', true), ''),
                NULLIF(current_setting('app.motif', true), ''));
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_hist_statut_entreprise ON entreprise;
CREATE TRIGGER trg_hist_statut_entreprise
    AFTER INSERT OR UPDATE OF statut ON entreprise
    FOR EACH ROW EXECUTE FUNCTION trg_historique_statut_entreprise();

-- Etat initial des comptes existants (une seule fois).
INSERT INTO historique_statut_entreprise (entreprise_id, ancien_statut, nouveau_statut, motif)
SELECT e.id, NULL, e.statut, 'etat_initial'
FROM entreprise e
WHERE NOT EXISTS (SELECT 1 FROM historique_statut_entreprise h WHERE h.entreprise_id = e.id);