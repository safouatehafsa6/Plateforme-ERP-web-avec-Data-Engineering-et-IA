-- 012_achats_metier.sql
-- Chaîne achats : demande d'achat -> bon de commande fournisseur -> réception.
-- Complète la table achat existante sans casser les données historiques.

CREATE SEQUENCE IF NOT EXISTS seq_demande_achat_numero START 1;
CREATE SEQUENCE IF NOT EXISTS seq_achat_numero START 1;
CREATE SEQUENCE IF NOT EXISTS seq_reception_achat_numero START 1;

CREATE TABLE IF NOT EXISTS demande_achat (
    id                SERIAL PRIMARY KEY,
    numero            VARCHAR(50) UNIQUE NOT NULL,
    demandeur_id      INTEGER REFERENCES utilisateur(id),
    date_demande      TIMESTAMP NOT NULL DEFAULT NOW(),
    statut            VARCHAR(30) NOT NULL DEFAULT 'brouillon',
    montant_estime    NUMERIC(12,2) NOT NULL DEFAULT 0,
    notes             TEXT,
    date_modification TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT demande_achat_statut_check CHECK (statut IN ('brouillon','soumise','convertie','annulee'))
);

CREATE TABLE IF NOT EXISTS ligne_demande_achat (
    id              SERIAL PRIMARY KEY,
    demande_id      INTEGER NOT NULL REFERENCES demande_achat(id) ON DELETE CASCADE,
    produit_id      INTEGER NOT NULL REFERENCES produit(id),
    quantite        INTEGER NOT NULL CHECK (quantite > 0),
    prix_estime     NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (prix_estime >= 0)
);

ALTER TABLE achat ADD COLUMN IF NOT EXISTS numero VARCHAR(50);
ALTER TABLE achat ADD COLUMN IF NOT EXISTS demande_id INTEGER REFERENCES demande_achat(id);
ALTER TABLE achat ADD COLUMN IF NOT EXISTS notes TEXT;
ALTER TABLE achat ADD COLUMN IF NOT EXISTS date_modification TIMESTAMP NOT NULL DEFAULT NOW();

UPDATE achat
SET numero = 'ACH-' || TO_CHAR(COALESCE(date_achat, NOW()), 'YYYY') || '-' || LPAD(id::text, 6, '0')
WHERE numero IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_achat_numero ON achat(numero);
CREATE INDEX IF NOT EXISTS ix_demande_achat_demandeur ON demande_achat(demandeur_id);
CREATE INDEX IF NOT EXISTS ix_achat_fournisseur ON achat(fournisseur_id);
CREATE INDEX IF NOT EXISTS ix_achat_demande ON achat(demande_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'achat_statut_metier_check'
    ) THEN
        ALTER TABLE achat ADD CONSTRAINT achat_statut_metier_check
        CHECK (statut IN ('en_cours','commande','reception_partielle','receptionne','facture','annulee'));
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS reception_achat (
    id              SERIAL PRIMARY KEY,
    achat_id        INTEGER NOT NULL REFERENCES achat(id),
    numero          VARCHAR(50) UNIQUE NOT NULL,
    date_reception  TIMESTAMP NOT NULL DEFAULT NOW(),
    statut          VARCHAR(30) NOT NULL DEFAULT 'receptionnee',
    notes           TEXT,
    CONSTRAINT reception_achat_statut_check CHECK (statut IN ('receptionnee','annulee'))
);

CREATE TABLE IF NOT EXISTS ligne_reception_achat (
    id                  SERIAL PRIMARY KEY,
    reception_id        INTEGER NOT NULL REFERENCES reception_achat(id) ON DELETE CASCADE,
    produit_id          INTEGER NOT NULL REFERENCES produit(id),
    quantite            INTEGER NOT NULL CHECK (quantite > 0)
);

CREATE INDEX IF NOT EXISTS ix_reception_achat_achat ON reception_achat(achat_id);
CREATE INDEX IF NOT EXISTS ix_ligne_reception_achat_reception ON ligne_reception_achat(reception_id);
