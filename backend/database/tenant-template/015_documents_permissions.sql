-- Module RBAC "documents" (import / consultation / suppression des documents du RAG).
-- Idempotent. À exécuter APRÈS 008 : le rôle Admin reçoit toutes les permissions.
--   documents.creer      -> importer un document
--   documents.consulter  -> lister les documents et les interroger via l'assistant
--   documents.supprimer  -> supprimer un document

INSERT INTO permission (module, action)
SELECT 'documents', a.action
FROM (VALUES ('consulter'), ('creer'), ('modifier'), ('supprimer'), ('valider'), ('exporter')) AS a(action)
WHERE NOT EXISTS (
    SELECT 1 FROM permission p WHERE p.module = 'documents' AND p.action = a.action
);

INSERT INTO role_permission (role_id, permission_id)
SELECT r.id, p.id
FROM role r
CROSS JOIN permission p
WHERE r.nom = 'Admin' AND p.module = 'documents'
AND NOT EXISTS (
    SELECT 1 FROM role_permission rp WHERE rp.role_id = r.id AND rp.permission_id = p.id
);
