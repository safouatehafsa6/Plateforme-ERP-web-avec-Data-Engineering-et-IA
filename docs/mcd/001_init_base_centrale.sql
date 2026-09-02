-- Script d'initialisation de la base centrale
-- Genere depuis docs/mcd/01-mcd-mld.md

CREATE TABLE super_admin (
    id              SERIAL PRIMARY KEY,
    nom             VARCHAR(100) NOT NULL,
    email           VARCHAR(150) UNIQUE NOT NULL,
    mot_de_passe    VARCHAR(255) NOT NULL,
    date_creation   TIMESTAMP DEFAULT NOW()
);

CREATE TABLE entreprise (
    id                  SERIAL PRIMARY KEY,
    nom                 VARCHAR(150) NOT NULL,
    secteur             VARCHAR(100),
    identifiant_unique  VARCHAR(50) UNIQUE NOT NULL,      -- ex: 147258K
    nom_base            VARCHAR(100) UNIQUE NOT NULL,     -- ex: societe_alpha
    statut              VARCHAR(30) NOT NULL DEFAULT 'inscrite',
        -- valeurs possibles : inscrite, otp_valide, kyc_en_attente, kyc_valide,
        -- kyc_rejete, essai, attente_paiement, active, suspendue, resiliee, expiree
    email_contact       VARCHAR(150) NOT NULL,
    telephone_contact    VARCHAR(30),
    date_creation       TIMESTAMP DEFAULT NOW()
);

CREATE TABLE abonnement (
    id              SERIAL PRIMARY KEY,
    entreprise_id   INTEGER NOT NULL REFERENCES entreprise(id) ON DELETE CASCADE,
    type_plan       VARCHAR(50) NOT NULL,        -- ex: Essai, Standard, Premium
    date_debut      DATE,
    date_fin        DATE,
    montant         NUMERIC(10,2),
    statut          VARCHAR(30) NOT NULL DEFAULT 'en_attente'
);

CREATE TABLE licence (
    id              SERIAL PRIMARY KEY,
    entreprise_id   INTEGER NOT NULL REFERENCES entreprise(id) ON DELETE CASCADE,
    type_licence    VARCHAR(50) NOT NULL,
    nb_utilisateurs_max INTEGER,
    date_expiration DATE
);

CREATE TABLE parametre_global (
    id      SERIAL PRIMARY KEY,
    cle     VARCHAR(100) UNIQUE NOT NULL,
    valeur  TEXT
);

CREATE TABLE journal_audit (
    id              SERIAL PRIMARY KEY,
    entreprise_id   INTEGER REFERENCES entreprise(id) ON DELETE SET NULL,
    acteur          VARCHAR(150),          -- email ou identifiant de qui a agi
    action          VARCHAR(150) NOT NULL, -- ex: "connexion", "changement_statut"
    details         TEXT,
    date_action     TIMESTAMP DEFAULT NOW()
);
