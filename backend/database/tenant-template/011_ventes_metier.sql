-- 011_ventes_metier.sql
-- Chaîne commerciale : devis -> commande -> bon de livraison -> facture.
-- Idempotent autant que possible afin de pouvoir être rejoué sur une base tenant.

CREATE SEQUENCE IF NOT EXISTS seq_devis_numero START 1;
CREATE SEQUENCE IF NOT EXISTS seq_commande_numero START 1;
CREATE SEQUENCE IF NOT EXISTS seq_bl_numero START 1;
CREATE SEQUENCE IF NOT EXISTS seq_facture_numero START 1;

CREATE TABLE IF NOT EXISTS devis (
    id              SERIAL PRIMARY KEY,
    client_id       INTEGER NOT NULL REFERENCES client(id),
    numero          VARCHAR(50) UNIQUE NOT NULL,
    date_devis      TIMESTAMP NOT NULL DEFAULT NOW(),
    date_validite   DATE,
    statut          VARCHAR(30) NOT NULL DEFAULT 'brouillon',
    montant_total   NUMERIC(12,2) NOT NULL DEFAULT 0,
    notes           TEXT,
    date_creation   TIMESTAMP NOT NULL DEFAULT NOW(),
    date_modification TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT devis_statut_check CHECK (statut IN ('brouillon','envoye','accepte','refuse','expire','annule'))
);

CREATE TABLE IF NOT EXISTS ligne_devis (
    id              SERIAL PRIMARY KEY,
    devis_id        INTEGER NOT NULL REFERENCES devis(id) ON DELETE CASCADE,
    produit_id      INTEGER NOT NULL REFERENCES produit(id),
    quantite        INTEGER NOT NULL CHECK (quantite > 0),
    prix_unitaire   NUMERIC(10,2) NOT NULL CHECK (prix_unitaire >= 0),
    remise_pct      NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (remise_pct >= 0 AND remise_pct <= 100)
);

ALTER TABLE commande ADD COLUMN IF NOT EXISTS numero VARCHAR(50);
ALTER TABLE commande ADD COLUMN IF NOT EXISTS devis_id INTEGER REFERENCES devis(id);
ALTER TABLE commande ADD COLUMN IF NOT EXISTS notes TEXT;
ALTER TABLE commande ADD COLUMN IF NOT EXISTS date_modification TIMESTAMP NOT NULL DEFAULT NOW();

UPDATE commande
SET numero = 'CMD-' || TO_CHAR(COALESCE(date_commande, NOW()), 'YYYY') || '-' || LPAD(id::text, 6, '0')
WHERE numero IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_commande_numero ON commande(numero);
CREATE UNIQUE INDEX IF NOT EXISTS ux_commande_devis ON commande(devis_id) WHERE devis_id IS NOT NULL;

ALTER TABLE ligne_commande ADD COLUMN IF NOT EXISTS remise_pct NUMERIC(5,2) NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS bon_livraison (
    id              SERIAL PRIMARY KEY,
    commande_id     INTEGER NOT NULL REFERENCES commande(id),
    numero          VARCHAR(50) UNIQUE NOT NULL,
    date_livraison  TIMESTAMP NOT NULL DEFAULT NOW(),
    statut          VARCHAR(30) NOT NULL DEFAULT 'prepare',
    adresse_livraison TEXT,
    notes           TEXT,
    CONSTRAINT bl_statut_check CHECK (statut IN ('prepare','expedie','livre','annule'))
);

CREATE TABLE IF NOT EXISTS ligne_bon_livraison (
    id                SERIAL PRIMARY KEY,
    bon_livraison_id  INTEGER NOT NULL REFERENCES bon_livraison(id) ON DELETE CASCADE,
    produit_id        INTEGER NOT NULL REFERENCES produit(id),
    quantite          INTEGER NOT NULL CHECK (quantite > 0)
);

-- Une facture conserve ses lignes propres : elles restent stables même si
-- les prix produits ou la commande source sont modifiés plus tard.
CREATE TABLE IF NOT EXISTS ligne_facture (
    id              SERIAL PRIMARY KEY,
    facture_id      INTEGER NOT NULL REFERENCES facture(id) ON DELETE CASCADE,
    produit_id      INTEGER NOT NULL REFERENCES produit(id),
    designation     VARCHAR(150) NOT NULL,
    quantite        INTEGER NOT NULL CHECK (quantite > 0),
    prix_unitaire   NUMERIC(10,2) NOT NULL CHECK (prix_unitaire >= 0),
    remise_pct      NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (remise_pct >= 0 AND remise_pct <= 100)
);

CREATE INDEX IF NOT EXISTS ix_devis_client ON devis(client_id);
CREATE INDEX IF NOT EXISTS ix_commande_client ON commande(client_id);
CREATE INDEX IF NOT EXISTS ix_bl_commande ON bon_livraison(commande_id);
CREATE INDEX IF NOT EXISTS ix_facture_commande ON facture(commande_id);

-- Le profil commercial doit pouvoir mener la chaîne de vente jusqu'à la facture.
INSERT INTO role_permission (role_id, permission_id)
SELECT r.id, p.id
FROM role r
JOIN permission p ON p.module = 'facturation' AND p.action IN ('consulter','creer','valider','exporter')
WHERE r.nom = 'Responsable Commercial'
AND NOT EXISTS (
    SELECT 1 FROM role_permission rp WHERE rp.role_id=r.id AND rp.permission_id=p.id
);
