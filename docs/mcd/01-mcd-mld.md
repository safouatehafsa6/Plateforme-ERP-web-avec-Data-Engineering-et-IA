# Modèle de données — MCD / MLD

> Traduction du diagramme de classes en tables concrètes, prêtes à être
> créées dans PostgreSQL. Deux schémas distincts, conformément à
> l'architecture multi-tenant : la **base centrale** (une seule, pour toute
> la plateforme) et le **schéma type d'une base entreprise** (dupliqué à
> l'identique pour chaque nouvelle entreprise cliente).

---

## 1. Base centrale (`Base_Centrale`)

### Modèle conceptuel

```
SuperAdmin (1) ---- (N) JournalAudit
Entreprise (1) ---- (1) Abonnement
Entreprise (1) ---- (N) Licence
Entreprise (1) ---- (N) JournalAudit
```

### Tables

| Table | Rôle |
|---|---|
| `super_admin` | Comptes des administrateurs de la plateforme |
| `entreprise` | Fiche d'identité de chaque entreprise cliente, avec le lien vers sa base dédiée |
| `abonnement` | Plan et statut de facturation de chaque entreprise |
| `licence` | Licences/limites associées à une entreprise |
| `parametre_global` | Paramètres de configuration de la plateforme |
| `journal_audit` | Historique des actions sensibles (connexions, changements de statut...) |

### Scripts SQL

```sql
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
```

---

## 2. Schéma type d'une base entreprise (ex: `societe_alpha`)

Ce schéma est **dupliqué automatiquement** à chaque activation d'une
nouvelle entreprise (voir diagramme de séquence d'onboarding).

### Modèle conceptuel

```
Role (1) ---- (N) Utilisateur
Role (N) ---- (N) Permission [via role_permission]
Departement (1) ---- (N) Utilisateur

Client (1) ---- (N) Commande ---- (N) LigneCommande ---- (1) Produit
Commande (1) ---- (1) Facture ---- (N) Paiement

Fournisseur (1) ---- (N) Achat ---- (N) LigneAchat ---- (1) Produit
Produit (1) ---- (N) MouvementStock
```

### Tables

| Table | Rôle |
|---|---|
| `role`, `permission`, `role_permission` | Gestion des droits (RBAC) |
| `departement` | Organisation interne de l'entreprise |
| `utilisateur` | Comptes des employés de l'entreprise |
| `client`, `fournisseur` | Entités métier (pas des utilisateurs du système) |
| `produit` | Catalogue produits/services |
| `commande`, `ligne_commande` | Ventes |
| `achat`, `ligne_achat` | Achats |
| `facture`, `paiement` | Facturation et encaissement |
| `mouvement_stock` | Historique des entrées/sorties de stock |

### Scripts SQL

```sql
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
```

---

## 3. Où placer ces scripts dans le projet

```
data-engineering/       (déjà existant)
backend/
└── database/
    ├── central/
    │   └── 001_init_base_centrale.sql   ← script de la section 1
    └── tenant-template/
        └── 001_init_schema_entreprise.sql   ← script de la section 2
```

Le script `tenant-template` est celui que le service de **provisioning**
(vu dans le diagramme de séquence d'onboarding) exécutera automatiquement
sur chaque nouvelle base créée pour une entreprise.

## 4. Prochaine étape

1. Créer ces fichiers `.sql` dans le dépôt.
2. Exécuter le script de la base centrale dans le conteneur `postgres-erp`
   (déjà présent dans `docker-compose.yml`).
3. Tester manuellement la création d'une base entreprise avec le script
   `tenant-template`, pour valider que tout fonctionne avant de l'automatiser
   dans le backend.
