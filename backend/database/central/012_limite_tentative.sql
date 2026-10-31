-- 012_limite_tentative.sql
-- Migration a executer sur la BASE CENTRALE (aussi appliquee automatiquement,
-- et sans risque, au demarrage du backend : tout est idempotent).
--
-- Compteurs d'echecs de connexion PERSISTANTS (ils survivent a un
-- redemarrage du backend). Cles : « email:<email> » (captcha progressif),
-- « ei:<email>|<ip> » et « ip:<ip> » (verrouillage temporaire).
CREATE TABLE IF NOT EXISTS limite_tentative (
    cle      VARCHAR(400) PRIMARY KEY,
    echecs   INTEGER     NOT NULL DEFAULT 0,
    derniere TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_limite_tentative_derniere ON limite_tentative (derniere);
