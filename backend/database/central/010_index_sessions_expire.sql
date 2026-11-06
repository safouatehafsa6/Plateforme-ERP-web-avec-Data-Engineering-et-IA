-- 010_index_sessions_expire.sql
-- Migration a executer sur la BASE CENTRALE (aussi appliquee automatiquement
-- au demarrage du backend). Accelere le nettoyage des sessions expirees.
CREATE INDEX IF NOT EXISTS idx_session_utilisateur_expire
    ON session_utilisateur (expire_le);
