-- 021 : registre extensible des règles métier, historique et anomalies.
-- Aucun taux légal n'est imposé : TVA_DEFAUT démarre à 0 % et doit être paramétré.
ALTER TABLE produit ADD COLUMN IF NOT EXISTS taux_tva NUMERIC(7,4);
ALTER TABLE facture ADD COLUMN IF NOT EXISTS montant_ht NUMERIC(12,2) NOT NULL DEFAULT 0;
ALTER TABLE facture ADD COLUMN IF NOT EXISTS montant_tva NUMERIC(12,2) NOT NULL DEFAULT 0;
ALTER TABLE facture ADD COLUMN IF NOT EXISTS date_echeance DATE;
ALTER TABLE facture ADD COLUMN IF NOT EXISTS montant_penalite NUMERIC(12,2) NOT NULL DEFAULT 0;
ALTER TABLE achat ADD COLUMN IF NOT EXISTS montant_ht NUMERIC(12,2) NOT NULL DEFAULT 0;
ALTER TABLE achat ADD COLUMN IF NOT EXISTS montant_tva NUMERIC(12,2) NOT NULL DEFAULT 0;
ALTER TABLE ligne_achat ADD COLUMN IF NOT EXISTS remise_pct NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (remise_pct >= 0 AND remise_pct <= 100);

CREATE TABLE IF NOT EXISTS regle_calcul_metier (
 id BIGSERIAL PRIMARY KEY,
 code VARCHAR(60) NOT NULL,
 libelle VARCHAR(160) NOT NULL,
 type_regle VARCHAR(30) NOT NULL CHECK (type_regle IN ('tva','remise','penalite','taux','autre')),
 module_source VARCHAR(40) NOT NULL DEFAULT 'general',
 taux NUMERIC(9,4) NOT NULL DEFAULT 0 CHECK (taux >= 0 AND taux <= 100),
 priorite INTEGER NOT NULL DEFAULT 0,
 actif BOOLEAN NOT NULL DEFAULT TRUE,
 date_debut DATE,
 date_fin DATE,
 configuration JSONB NOT NULL DEFAULT '{}'::jsonb,
 cree_par VARCHAR(200),
 cree_le TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 modifie_le TIMESTAMPTZ,
 CONSTRAINT regle_calcul_dates_chk CHECK (date_fin IS NULL OR date_debut IS NULL OR date_fin >= date_debut)
);
CREATE INDEX IF NOT EXISTS ix_regle_calcul_code_actif ON regle_calcul_metier(code,actif,priorite DESC);
CREATE TABLE IF NOT EXISTS historique_calcul_metier (
 id BIGSERIAL PRIMARY KEY,
 module_source VARCHAR(40) NOT NULL,
 type_document VARCHAR(40) NOT NULL,
 document_id BIGINT NOT NULL,
 reference VARCHAR(80),
 montant_ht NUMERIC(18,2) NOT NULL,
 montant_tva NUMERIC(18,2) NOT NULL,
 montant_ttc NUMERIC(18,2) NOT NULL,
 details JSONB NOT NULL,
 cree_par VARCHAR(200),
 cree_le TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(module_source,type_document,document_id)
);
CREATE INDEX IF NOT EXISTS ix_historique_calcul_recent ON historique_calcul_metier(cree_le DESC);
CREATE TABLE IF NOT EXISTS anomalie_calcul_metier (
 id BIGSERIAL PRIMARY KEY,
 module_source VARCHAR(40) NOT NULL,
 type_document VARCHAR(40) NOT NULL,
 document_id BIGINT NOT NULL,
 code VARCHAR(60) NOT NULL,
 gravite VARCHAR(20) NOT NULL DEFAULT 'attention',
 message TEXT NOT NULL,
 details JSONB NOT NULL DEFAULT '{}'::jsonb,
 statut VARCHAR(20) NOT NULL DEFAULT 'nouvelle',
 cree_le TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 CONSTRAINT anomalie_calcul_statut_chk CHECK (statut IN ('nouvelle','examinee','ignoree'))
);
CREATE INDEX IF NOT EXISTS ix_anomalie_calcul_recent ON anomalie_calcul_metier(statut,cree_le DESC);
INSERT INTO regle_calcul_metier(code,libelle,type_regle,module_source,taux,priorite,configuration)
SELECT 'TVA_DEFAUT','TVA par défaut (à configurer)','tva','general',0,0,'{"note":"Configurer selon le régime fiscal applicable"}'::jsonb
WHERE NOT EXISTS (SELECT 1 FROM regle_calcul_metier WHERE code='TVA_DEFAUT');
INSERT INTO permission(module,action)
SELECT 'calculs',a.action FROM (VALUES ('consulter'),('creer'),('modifier')) a(action)
WHERE NOT EXISTS (SELECT 1 FROM permission p WHERE p.module='calculs' AND p.action=a.action);
INSERT INTO role_permission(role_id,permission_id)
SELECT r.id,p.id FROM role r JOIN permission p ON p.module='calculs'
WHERE r.nom='Admin' AND NOT EXISTS (SELECT 1 FROM role_permission rp WHERE rp.role_id=r.id AND rp.permission_id=p.id);


-- Éviter les doublons d'anomalies pour un même document et un même code.
-- En cas de doublons existants, conserver l'enregistrement le plus récent.

DELETE FROM anomalie_calcul_metier a
USING anomalie_calcul_metier b
WHERE a.module_source = b.module_source
  AND a.type_document = b.type_document
  AND a.document_id = b.document_id
  AND a.code = b.code
  AND a.id < b.id;

CREATE UNIQUE INDEX IF NOT EXISTS uq_anomalie_calcul_document_code
ON anomalie_calcul_metier (
    module_source,
    type_document,
    document_id,
    code
);