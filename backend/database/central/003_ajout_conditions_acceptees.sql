-- Migration : traçabilité de l'acceptation des conditions d'utilisation
-- (voir email entreprise, section 7 : date, heure et version des CGU
-- acceptées doivent être enregistrées).
-- Sans effet si déjà appliqué (IF NOT EXISTS).

ALTER TABLE entreprise
    ADD COLUMN IF NOT EXISTS conditions_acceptees_le TIMESTAMP,
    ADD COLUMN IF NOT EXISTS conditions_version VARCHAR(20),
    ADD COLUMN IF NOT EXISTS numero_identification_fiscale VARCHAR(50),
    ADD COLUMN IF NOT EXISTS numero_cin VARCHAR(30);
