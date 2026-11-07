ALTER TABLE abonnement
    ADD COLUMN IF NOT EXISTS connexions_essai_max INTEGER
        CHECK (connexions_essai_max IS NULL OR connexions_essai_max > 0),
    ADD COLUMN IF NOT EXISTS connexions_essai_utilisees INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS essai_bloque_le TIMESTAMPTZ;

-- Consomme une connexion d'essai pour l'abonnement le plus recent de
-- l'entreprise. Appelee APRES verification du mot de passe, AVANT emettre_jeton.
-- Le verrou de ligne est libere au commit de l'appelant.
CREATE OR REPLACE FUNCTION consommer_connexion_essai(p_entreprise_id INTEGER)
RETURNS TABLE (essai BOOLEAN, autorise BOOLEAN, utilisees INTEGER, maximum INTEGER) AS $$
DECLARE
    v_id   INTEGER;
    v_max  INTEGER;
    v_util INTEGER;
BEGIN
    SELECT a.id, a.connexions_essai_max, a.connexions_essai_utilisees
      INTO v_id, v_max, v_util
      FROM abonnement a
     WHERE a.entreprise_id = p_entreprise_id
     ORDER BY a.id DESC
     LIMIT 1
       FOR UPDATE;

    IF v_id IS NULL OR v_max IS NULL THEN
        RETURN QUERY SELECT FALSE, TRUE, 0, 0;
        RETURN;
    END IF;

    IF v_util >= v_max THEN
        UPDATE abonnement SET essai_bloque_le = COALESCE(essai_bloque_le, NOW()) WHERE id = v_id;
        RETURN QUERY SELECT TRUE, FALSE, v_util, v_max;
        RETURN;
    END IF;

    UPDATE abonnement SET connexions_essai_utilisees = connexions_essai_utilisees + 1 WHERE id = v_id;
    RETURN QUERY SELECT TRUE, TRUE, v_util + 1, v_max;
END;
$$ LANGUAGE plpgsql;