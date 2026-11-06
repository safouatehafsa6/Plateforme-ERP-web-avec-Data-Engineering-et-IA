-- Module Prospects & suivi commercial.
-- Idempotent : peut être rejoué sur une base existante (voir app/scripts/migrate_prospects.py).
--
--  * prospect          : contacts commerciaux avant conversion en client
--  * suivi_commercial  : historique daté et NON MODIFIABLE (prospects et clients)
--  * client            : colonnes d'archivage (archivage logique, aucune suppression)

CREATE TABLE IF NOT EXISTS prospect (
    id                       SERIAL PRIMARY KEY,
    nom                      VARCHAR(150) NOT NULL,
    contact                  VARCHAR(150),
    email                    VARCHAR(150),
    telephone                VARCHAR(30),
    adresse                  TEXT,
    source                   VARCHAR(30) NOT NULL DEFAULT 'autre',
    statut                   VARCHAR(20) NOT NULL DEFAULT 'nouveau',
    besoin                   TEXT,
    responsable_id           INTEGER REFERENCES utilisateur(id) ON DELETE SET NULL,
    cree_par                 INTEGER REFERENCES utilisateur(id) ON DELETE SET NULL,
    client_id                INTEGER REFERENCES client(id),
    date_conversion          TIMESTAMPTZ,
    prochaine_relance_le     DATE,
    derniere_interaction_le  TIMESTAMPTZ,
    archive                  BOOLEAN NOT NULL DEFAULT FALSE,
    archive_le               TIMESTAMPTZ,
    archive_motif            TEXT,
    archive_par              INTEGER REFERENCES utilisateur(id) ON DELETE SET NULL,
    cree_le                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    mis_a_jour_le            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT prospect_statut_chk CHECK (statut IN ('nouveau','contacte','qualifie','perdu','converti')),
    CONSTRAINT prospect_source_chk CHECK (source IN ('site_web','recommandation','salon','appel_entrant','reseaux_sociaux','campagne','autre')),
    CONSTRAINT prospect_contact_chk CHECK (email IS NOT NULL OR telephone IS NOT NULL),
    CONSTRAINT prospect_converti_chk CHECK ((statut = 'converti') = (client_id IS NOT NULL))
);

-- Dernier rempart contre les doublons (accès concurrents) : l'application les détecte
-- d'abord pour donner un message clair. Les prospects archivés restent comptés.
CREATE UNIQUE INDEX IF NOT EXISTS ux_prospect_email
    ON prospect (LOWER(email)) WHERE email IS NOT NULL;
-- Clé téléphone = 8 derniers chiffres (+216 12 345 678 == 0012345678 == 12345678).
CREATE UNIQUE INDEX IF NOT EXISTS ux_prospect_telephone
    ON prospect ((right(regexp_replace(telephone, '[^0-9]', '', 'g'), 8))) WHERE telephone IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_prospect_statut ON prospect (archive, statut);
CREATE INDEX IF NOT EXISTS ix_prospect_responsable ON prospect (responsable_id);
CREATE INDEX IF NOT EXISTS ix_prospect_client ON prospect (client_id);

CREATE TABLE IF NOT EXISTS suivi_commercial (
    id              BIGSERIAL PRIMARY KEY,
    entite_type     VARCHAR(10) NOT NULL,
    entite_id       INTEGER NOT NULL,
    type_evenement  VARCHAR(20) NOT NULL,
    contenu         TEXT,
    details         JSONB NOT NULL DEFAULT '{}'::jsonb,
    date_evenement  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    enregistre_le   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    auteur_id       INTEGER,
    auteur_nom      VARCHAR(200),
    CONSTRAINT suivi_entite_chk CHECK (entite_type IN ('prospect','client')),
    CONSTRAINT suivi_type_chk CHECK (type_evenement IN (
        'creation','modification','statut','conversion','archivage','reactivation',
        'appel','email','rendez_vous','note','relance'))
);
CREATE INDEX IF NOT EXISTS ix_suivi_entite
    ON suivi_commercial (entite_type, entite_id, date_evenement DESC, id DESC);

-- Historique en ajout seul : ni modification ni suppression d'une ligne existante.
CREATE OR REPLACE FUNCTION suivi_commercial_immuable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'L''historique commercial est en ajout seul : modification et suppression interdites.';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_suivi_commercial_immuable ON suivi_commercial;
CREATE TRIGGER trg_suivi_commercial_immuable
    BEFORE UPDATE OR DELETE ON suivi_commercial
    FOR EACH ROW EXECUTE FUNCTION suivi_commercial_immuable();

-- Archivage logique des clients (les commandes, devis et factures restent intacts).
ALTER TABLE client ADD COLUMN IF NOT EXISTS archive BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE client ADD COLUMN IF NOT EXISTS archive_le TIMESTAMPTZ;
ALTER TABLE client ADD COLUMN IF NOT EXISTS archive_motif TEXT;
ALTER TABLE client ADD COLUMN IF NOT EXISTS archive_par INTEGER REFERENCES utilisateur(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS ix_client_archive ON client (archive);
