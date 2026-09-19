-- 005_type_compte_index.sql
-- Migration a executer sur la BASE CENTRALE.
--
-- Le point d'entree unique de connexion doit savoir, une fois l'email
-- retrouve dans compte_index, dans QUELLE table de la base entreprise
-- chercher le compte : "utilisateur" (Admin/collaborateur interne) ou
-- "utilisateur_externe" (client/partenaire via le portail externe).

ALTER TABLE compte_index
    ADD COLUMN IF NOT EXISTS type_compte VARCHAR(20) NOT NULL DEFAULT 'interne';
    -- valeurs possibles : interne, externe
