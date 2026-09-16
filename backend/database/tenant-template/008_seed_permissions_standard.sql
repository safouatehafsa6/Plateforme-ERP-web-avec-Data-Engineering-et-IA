-- Migration à exécuter sur CHAQUE base entreprise, pour peupler la table
-- `permission` avec les 6 niveaux standard (consultation, création,
-- modification, suppression, validation, export) sur chaque module
-- métier — socle du moteur RBAC décrit dans le document de profils
-- utilisateurs transmis par l'entreprise.

DO $$
DECLARE
    modules TEXT[] := ARRAY['ventes', 'achats', 'stock', 'clients', 'fournisseurs', 'facturation', 'comptabilite', 'utilisateurs'];
    actions TEXT[] := ARRAY['consultation', 'creation', 'modification', 'suppression', 'validation', 'export'];
    m TEXT;
    a TEXT;
BEGIN
    FOREACH m IN ARRAY modules LOOP
        FOREACH a IN ARRAY actions LOOP
            INSERT INTO permission (module, action)
            SELECT m, a
            WHERE NOT EXISTS (
                SELECT 1 FROM permission WHERE module = m AND action = a
            );
        END LOOP;
    END LOOP;
END $$;
