-- Migration à exécuter sur CHAQUE base entreprise déjà créée (pas la
-- base centrale), pour garantir qu'un rôle "Admin" existe — nécessaire
-- pour que le contrôle d'accès (exiger_role_admin) fonctionne sur les
-- comptes administrateurs déjà provisionnés avant cette évolution.
--
-- Exemple d'exécution (à adapter au nom réel de la base) :
--   docker compose exec postgres-erp psql -U erp_user -d compte_xxx_xxx \
--     -f /docker-entrypoint-initdb.d/007_role_admin_par_defaut.sql

INSERT INTO role (nom, description)
SELECT 'Admin', 'Administrateur de l''entreprise, tous droits'
WHERE NOT EXISTS (SELECT 1 FROM role WHERE nom = 'Admin');

-- Rattache l'utilisateur administrateur existant (créé au provisioning,
-- généralement sans role_id) à ce rôle Admin, s'il n'a pas déjà de rôle.
UPDATE utilisateur
SET role_id = (SELECT id FROM role WHERE nom = 'Admin')
WHERE role_id IS NULL;
