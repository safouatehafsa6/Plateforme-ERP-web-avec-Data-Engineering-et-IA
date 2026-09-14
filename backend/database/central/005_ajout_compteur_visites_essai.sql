-- Migration : compteur de visites pour la période d'essai gratuite
-- (limite de 30 connexions, conformément à la demande de l'entreprise).

ALTER TABLE abonnement
    ADD COLUMN IF NOT EXISTS visites_utilisees INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS visites_max INTEGER;

-- Pour les abonnements de type Essai déjà existants, on fixe la limite
-- par défaut à 30 si elle n'est pas encore définie.
UPDATE abonnement SET visites_max = 30 WHERE type_plan ILIKE 'essai' AND visites_max IS NULL;
