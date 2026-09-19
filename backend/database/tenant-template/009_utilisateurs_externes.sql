-- 009_utilisateurs_externes.sql
-- Migration a executer sur CHAQUE base entreprise.
--
-- Portail Utilisateurs externes (voir lettre de cadrage, section 4) :
-- "Les Utilisateurs sont les tiers externes — clients, partenaires ou
-- toute autre partie prenante — que l'Administrateur Client choisit
-- d'integrer a son environnement via le portail externe dedie. Leurs
-- comptes sont crees, actives et administres exclusivement par
-- l'Administrateur Client."
--
-- Un utilisateur_externe est toujours rattache a une fiche client
-- existante (table "client") : c'est cette liaison qui determine quelles
-- factures/commandes lui sont visibles cote portail — jamais les
-- donnees internes de l'entreprise.

CREATE TABLE IF NOT EXISTS utilisateur_externe (
    id                     SERIAL PRIMARY KEY,
    client_id              INTEGER NOT NULL REFERENCES client(id) ON DELETE CASCADE,
    email                  VARCHAR(150) UNIQUE NOT NULL,
    mot_de_passe           VARCHAR(255) NOT NULL,
    actif                  BOOLEAN DEFAULT TRUE,
    mot_de_passe_a_changer BOOLEAN DEFAULT TRUE,
    date_creation          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_utilisateur_externe_client ON utilisateur_externe(client_id);
