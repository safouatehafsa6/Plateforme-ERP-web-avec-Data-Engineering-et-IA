-- Préconfigure les rôles métier décrits par l'entreprise (profils
-- "immédiatement opérationnels", modifiables ensuite librement par
-- l'Administrateur Client) et leurs permissions par défaut, sur les 6
-- niveaux : consulter, creer, modifier, supprimer, valider, exporter.
--
-- À exécuter sur chaque base entreprise (nouvelle via le provisioning
-- automatique, ou existante via une exécution manuelle une fois).

-- 1. Les modules et leurs 6 actions possibles (si pas déjà présents).
INSERT INTO permission (module, action)
SELECT m.module, a.action
FROM (VALUES ('ventes'), ('achats'), ('stock'), ('clients'), ('fournisseurs'), ('facturation'), ('comptabilite')) AS m(module)
CROSS JOIN (VALUES ('consulter'), ('creer'), ('modifier'), ('supprimer'), ('valider'), ('exporter')) AS a(action)
WHERE NOT EXISTS (
    SELECT 1 FROM permission p WHERE p.module = m.module AND p.action = a.action
);

-- 2. Les 4 profils préconfigurés (si pas déjà présents).
INSERT INTO role (nom, description)
SELECT nom, description FROM (VALUES
    ('Responsable Commercial', 'Prospection, devis, commandes, factures et suivi des règlements'),
    ('Responsable Financier et Comptable', 'Comptabilité, trésorerie, déclarations fiscales et états financiers'),
    ('Responsable des Stocks et Magasinier', 'Réceptions, mouvements de stock, inventaires et seuils d''alerte'),
    ('Responsable Achats', 'Fournisseurs, bons de commande et rapprochement des factures d''achat')
) AS v(nom, description)
WHERE NOT EXISTS (SELECT 1 FROM role WHERE role.nom = v.nom);

-- 3. Permissions par défaut de chaque profil (idempotent : ne duplique pas
-- si déjà attribué).
INSERT INTO role_permission (role_id, permission_id)
SELECT r.id, p.id
FROM role r
JOIN permission p ON (
    (r.nom = 'Responsable Commercial' AND (
        (p.module = 'ventes' AND p.action IN ('consulter','creer','modifier','valider','exporter')) OR
        (p.module = 'clients' AND p.action IN ('consulter','creer','modifier','exporter')) OR
        (p.module = 'stock' AND p.action = 'consulter')
    ))
    OR (r.nom = 'Responsable Financier et Comptable' AND (
        (p.module = 'comptabilite' AND p.action IN ('consulter','creer','modifier','valider','exporter')) OR
        (p.module = 'facturation' AND p.action IN ('consulter','valider','exporter')) OR
        (p.module = 'ventes' AND p.action = 'consulter') OR
        (p.module = 'achats' AND p.action = 'consulter')
    ))
    OR (r.nom = 'Responsable des Stocks et Magasinier' AND (
        (p.module = 'stock' AND p.action IN ('consulter','creer','modifier','supprimer','valider','exporter')) OR
        (p.module = 'achats' AND p.action = 'consulter')
    ))
    OR (r.nom = 'Responsable Achats' AND (
        (p.module = 'achats' AND p.action IN ('consulter','creer','modifier','valider','exporter')) OR
        (p.module = 'fournisseurs' AND p.action IN ('consulter','creer','modifier')) OR
        (p.module = 'stock' AND p.action = 'consulter')
    ))
)
WHERE NOT EXISTS (
    SELECT 1 FROM role_permission rp WHERE rp.role_id = r.id AND rp.permission_id = p.id
);

-- 4. Le rôle Admin (créé lors du provisioning) reçoit automatiquement
-- TOUTES les permissions existantes — cohérent avec sa description
-- ("l'unique détenteur de l'ensemble des droits").
INSERT INTO role_permission (role_id, permission_id)
SELECT r.id, p.id
FROM role r
CROSS JOIN permission p
WHERE r.nom = 'Admin'
AND NOT EXISTS (
    SELECT 1 FROM role_permission rp WHERE rp.role_id = r.id AND rp.permission_id = p.id
);
