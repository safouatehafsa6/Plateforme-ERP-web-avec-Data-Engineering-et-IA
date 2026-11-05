-- 007_evenement_securite.sql : journal des evenements de securite (ajout seul)
CREATE TABLE IF NOT EXISTS evenement_securite (
  id              BIGSERIAL PRIMARY KEY,
  cree_le         TIMESTAMPTZ NOT NULL DEFAULT now(),
  type_evenement  VARCHAR(40) NOT NULL,
  gravite         VARCHAR(20) NOT NULL DEFAULT 'info'
                  CHECK (gravite IN ('info','avertissement','critique')),
  succes          BOOLEAN,
  type_compte     VARCHAR(12),
  utilisateur_id  VARCHAR(64),
  email           VARCHAR(255),
  entreprise_id   VARCHAR(64),
  jti             VARCHAR(64),
  adresse_ip      INET,
  systeme         VARCHAR(60),
  navigateur      VARCHAR(60),
  acteur_email    VARCHAR(255),
  details         JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_evt_ent_date ON evenement_securite (entreprise_id, cree_le DESC);
CREATE INDEX IF NOT EXISTS ix_evt_email_dt ON evenement_securite (email, cree_le DESC);
CREATE INDEX IF NOT EXISTS ix_evt_type_dt  ON evenement_securite (type_evenement, cree_le DESC);

CREATE OR REPLACE FUNCTION evenement_securite_immuable() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' AND current_setting('erp.purge_autorisee', true) = 'on' THEN
    RETURN OLD;
  END IF;
  RAISE EXCEPTION 'evenement_securite est en ajout seul (UPDATE/DELETE interdits)';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_evt_immuable ON evenement_securite;
CREATE TRIGGER trg_evt_immuable BEFORE UPDATE OR DELETE ON evenement_securite
  FOR EACH ROW EXECUTE FUNCTION evenement_securite_immuable();

CREATE OR REPLACE FUNCTION purger_evenements_securite(retention INTERVAL DEFAULT '12 months')
RETURNS BIGINT AS $$
DECLARE n BIGINT;
BEGIN
  PERFORM set_config('erp.purge_autorisee', 'on', true);
  DELETE FROM evenement_securite WHERE cree_le < now() - retention;
  GET DIAGNOSTICS n = ROW_COUNT;
  PERFORM set_config('erp.purge_autorisee', 'off', true);
  RETURN n;
END;
$$ LANGUAGE plpgsql;