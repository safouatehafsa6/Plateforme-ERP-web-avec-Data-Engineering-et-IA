-- Permissions RBAC du module « prospects » (idempotent, à exécuter APRÈS 008).
--   consulter : liste, fiche, historique
--   creer     : créer un prospect, ajouter un suivi
--   modifier  : modifier la fiche, changer le statut
--   valider   : convertir un prospect en client
--   supprimer : archiver / réactiver (aucune suppression physique)
--   exporter  : réservé (export)
-- Archivage / réactivation d'un CLIENT : clients.supprimer.

INSERT INTO permission (module, action)
SELECT 'prospects', a.action
FROM (VALUES ('consulter'), ('creer'), ('modifier'), ('supprimer'), ('valider'), ('exporter')) AS a(action)
WHERE NOT EXISTS (SELECT 1 FROM permission p WHERE p.module = 'prospects' AND p.action = a.action);

INSERT INTO role_permission (role_id, permission_id)
SELECT r.id, p.id
FROM role r
JOIN permission p ON p.module = 'prospects'
WHERE (r.nom = 'Admin' OR r.nom = 'Responsable Commercial')
  AND NOT EXISTS (SELECT 1 FROM role_permission rp WHERE rp.role_id = r.id AND rp.permission_id = p.id);
