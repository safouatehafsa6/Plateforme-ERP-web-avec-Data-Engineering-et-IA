-- Script d'initialisation du schema type d'une entreprise
-- Genere depuis docs/mcd/01-mcd-mld.md
-- A executer sur chaque nouvelle base entreprise creee automatiquement

CREATE TABLE departement (
    id      SERIAL PRIMARY KEY,
    nom     VARCHAR(100) NOT NULL
);

CREATE TABLE role (
    id          SERIAL PRIMARY KEY,
    nom         VARCHAR(50) UNIQUE NOT NULL,  -- ex: Admin, Commercial, Comptable
    description TEXT
);

CREATE TABLE permission (
    id      SERIAL PRIMARY KEY,
    module  VARCHAR(50) NOT NULL,   -- ex: ventes, stock, comptabilite
    action  VARCHAR(50) NOT NULL    -- ex: consulter, creer, modifier, supprimer, valider, exporter
);

CREATE TABLE role_permission (
    role_id       INTEGER NOT NULL REFERENCES role(id) ON DELETE CASCADE,
    permission_id INTEGER NOT NULL REFERENCES permission(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE utilisateur (
    id              SERIAL PRIMARY KEY,
    nom             VARCHAR(100) NOT NULL,
    prenom          VARCHAR(100) NOT NULL,
    email           VARCHAR(150) UNIQUE NOT NULL,
    mot_de_passe    VARCHAR(255) NOT NULL,
    role_id         INTEGER REFERENCES role(id),
    departement_id  INTEGER REFERENCES departement(id),
    actif           BOOLEAN DEFAULT TRUE,
    date_creation   TIMESTAMP DEFAULT NOW()
);

CREATE TABLE client (
    id          SERIAL PRIMARY KEY,
    nom         VARCHAR(150) NOT NULL,
    email       VARCHAR(150),
    telephone   VARCHAR(30),
    adresse     TEXT
);

CREATE TABLE fournisseur (
    id          SERIAL PRIMARY KEY,
    nom         VARCHAR(150) NOT NULL,
    email       VARCHAR(150),
    telephone   VARCHAR(30),
    adresse     TEXT
);

CREATE TABLE produit (
    id              SERIAL PRIMARY KEY,
    reference       VARCHAR(50) UNIQUE NOT NULL,
    nom             VARCHAR(150) NOT NULL,
    categorie       VARCHAR(100),
    prix_unitaire   NUMERIC(10,2) NOT NULL,
    stock_actuel    INTEGER DEFAULT 0
);

CREATE TABLE commande (
    id              SERIAL PRIMARY KEY,
    client_id       INTEGER NOT NULL REFERENCES client(id),
    date_commande   TIMESTAMP DEFAULT NOW(),
    statut          VARCHAR(30) DEFAULT 'en_cours', -- devis, confirmee, livree, annulee
    montant_total   NUMERIC(12,2) DEFAULT 0
);

CREATE TABLE ligne_commande (
    id              SERIAL PRIMARY KEY,
    commande_id     INTEGER NOT NULL REFERENCES commande(id) ON DELETE CASCADE,
    produit_id      INTEGER NOT NULL REFERENCES produit(id),
    quantite        INTEGER NOT NULL,
    prix_unitaire   NUMERIC(10,2) NOT NULL
);

CREATE TABLE facture (
    id              SERIAL PRIMARY KEY,
    commande_id     INTEGER REFERENCES commande(id),
    numero          VARCHAR(50) UNIQUE NOT NULL,
    date_facture    TIMESTAMP DEFAULT NOW(),
    montant_total   NUMERIC(12,2) NOT NULL,
    statut          VARCHAR(30) DEFAULT 'impayee' -- impayee, payee, annulee
);

CREATE TABLE paiement (
    id          SERIAL PRIMARY KEY,
    facture_id  INTEGER NOT NULL REFERENCES facture(id) ON DELETE CASCADE,
    date_paiement TIMESTAMP DEFAULT NOW(),
    montant     NUMERIC(12,2) NOT NULL,
    methode     VARCHAR(50) -- carte, virement, especes
);

CREATE TABLE achat (
    id              SERIAL PRIMARY KEY,
    fournisseur_id  INTEGER NOT NULL REFERENCES fournisseur(id),
    date_achat      TIMESTAMP DEFAULT NOW(),
    statut          VARCHAR(30) DEFAULT 'en_cours', -- commande, receptionne, facture
    montant_total   NUMERIC(12,2) DEFAULT 0
);

CREATE TABLE ligne_achat (
    id              SERIAL PRIMARY KEY,
    achat_id        INTEGER NOT NULL REFERENCES achat(id) ON DELETE CASCADE,
    produit_id      INTEGER NOT NULL REFERENCES produit(id),
    quantite        INTEGER NOT NULL,
    prix_unitaire   NUMERIC(10,2) NOT NULL
);

CREATE TABLE mouvement_stock (
    id              SERIAL PRIMARY KEY,
    produit_id      INTEGER NOT NULL REFERENCES produit(id),
    type_mouvement  VARCHAR(20) NOT NULL, -- entree, sortie, ajustement
    quantite        INTEGER NOT NULL,
    date_mouvement  TIMESTAMP DEFAULT NOW(),
    reference_doc   VARCHAR(100) -- ex: numéro de commande ou d'achat lié
);
