-- Boutons flottants administrables (niveau PLATEFORME : un seul jeu de réglages pour tous les écrans,
-- publics et connectés). Géré par le Super Administrateur, sans intervention sur le code source.
-- Idempotent. Les boutons « système » par défaut sont insérés par l'application (services/boutons_flottants.py).

CREATE TABLE IF NOT EXISTS bouton_flottant_config (
    id              SMALLINT PRIMARY KEY CHECK (id = 1),          -- ligne unique
    actif           BOOLEAN NOT NULL DEFAULT TRUE,
    position        VARCHAR(20) NOT NULL DEFAULT 'auto',
    taille          VARCHAR(10) NOT NULL DEFAULT 'moyen',
    couleur         VARCHAR(7),
    icone           VARCHAR(30) NOT NULL DEFAULT 'headset',
    version         INTEGER NOT NULL DEFAULT 1,
    mis_a_jour_le   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    mis_a_jour_par  VARCHAR(200),
    CONSTRAINT bf_config_position_chk CHECK (position IN ('auto','bas-droite','bas-gauche','milieu-droite','milieu-gauche','haut-droite','haut-gauche')),
    CONSTRAINT bf_config_taille_chk CHECK (taille IN ('petit','moyen','grand')),
    CONSTRAINT bf_config_couleur_chk CHECK (couleur IS NULL OR couleur ~ '^#[0-9a-fA-F]{6}$')
);

CREATE TABLE IF NOT EXISTS bouton_flottant (
    id                SERIAL PRIMARY KEY,
    cle               VARCHAR(40) NOT NULL UNIQUE,
    titres            JSONB NOT NULL,
    icone             VARCHAR(30) NOT NULL,
    couleur           VARCHAR(7),
    taille            VARCHAR(10) NOT NULL DEFAULT 'moyen',
    placement         VARCHAR(10) NOT NULL DEFAULT 'menu',      -- 'menu' (dans le menu d'aide) ou 'libre' (bouton isolé)
    position          VARCHAR(20),                               -- ancrage d'un bouton 'libre'
    ordre             INTEGER NOT NULL DEFAULT 100,
    actif             BOOLEAN NOT NULL DEFAULT TRUE,
    action            VARCHAR(20) NOT NULL,
    cible             VARCHAR(500),
    nouvel_onglet     BOOLEAN NOT NULL DEFAULT FALSE,
    audience          VARCHAR(10) NOT NULL DEFAULT 'tous',      -- public (visiteur) / connecte / tous
    profils           TEXT[] NOT NULL DEFAULT '{}',              -- vide = tous les profils
    appareils         VARCHAR(10) NOT NULL DEFAULT 'tous',
    routes_incluses   TEXT[] NOT NULL DEFAULT '{}',              -- préfixes de pages ; vide = partout
    routes_exclues    TEXT[] NOT NULL DEFAULT '{}',
    affiche_du        TIMESTAMPTZ,
    affiche_jusqu_au  TIMESTAMPTZ,
    systeme           BOOLEAN NOT NULL DEFAULT FALSE,           -- bouton fourni d'origine : modifiable, non supprimable
    cree_le           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    mis_a_jour_le     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    mis_a_jour_par    VARCHAR(200),
    CONSTRAINT bf_taille_chk CHECK (taille IN ('petit','moyen','grand')),
    CONSTRAINT bf_placement_chk CHECK (placement IN ('menu','libre')),
    CONSTRAINT bf_position_chk CHECK (position IS NULL OR position IN ('bas-droite','bas-gauche','milieu-droite','milieu-gauche','haut-droite','haut-gauche')),
    CONSTRAINT bf_libre_position_chk CHECK (placement = 'menu' OR position IS NOT NULL),
    CONSTRAINT bf_action_chk CHECK (action IN ('assistant','notifications','support','theme','langue','route','url','whatsapp')),
    CONSTRAINT bf_audience_chk CHECK (audience IN ('public','connecte','tous')),
    CONSTRAINT bf_appareils_chk CHECK (appareils IN ('tous','mobile','ordinateur')),
    CONSTRAINT bf_couleur_chk CHECK (couleur IS NULL OR couleur ~ '^#[0-9a-fA-F]{6}$'),
    CONSTRAINT bf_dates_chk CHECK (affiche_du IS NULL OR affiche_jusqu_au IS NULL OR affiche_jusqu_au > affiche_du)
);
CREATE INDEX IF NOT EXISTS ix_bouton_flottant_ordre ON bouton_flottant (actif, ordre, id);

CREATE TABLE IF NOT EXISTS bouton_flottant_historique (
    id          BIGSERIAL PRIMARY KEY,
    cle         VARCHAR(40),
    operation   VARCHAR(20) NOT NULL,
    details     JSONB NOT NULL DEFAULT '{}'::jsonb,
    par_email   VARCHAR(200),
    le          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_bf_historique_recent ON bouton_flottant_historique (le DESC, id DESC);
