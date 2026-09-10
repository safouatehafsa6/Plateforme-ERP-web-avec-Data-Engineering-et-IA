-- Migration : traçabilité de l'acceptation des conditions d'utilisation
-- (date, heure et version acceptées), conformément à la recommandation
-- de l'entreprise sur l'inscription (section 7).

ALTER TABLE entreprise
    ADD COLUMN IF NOT EXISTS cgu_accepte_le TIMESTAMP,
    ADD COLUMN IF NOT EXISTS cgu_version VARCHAR(20);
