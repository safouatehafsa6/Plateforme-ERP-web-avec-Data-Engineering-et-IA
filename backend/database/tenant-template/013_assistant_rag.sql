-- RAG local par recherche plein texte PostgreSQL (une table par base entreprise).
-- Appliquer cette migration dans chaque base entreprise existante.
CREATE TABLE IF NOT EXISTS assistant_document_chunk (
    id BIGSERIAL PRIMARY KEY,
    document_id TEXT NOT NULL,
    titre TEXT NOT NULL,
    source TEXT NOT NULL,
    module TEXT NOT NULL DEFAULT 'documents',
    contenu TEXT NOT NULL,
    langue VARCHAR(5) NOT NULL DEFAULT 'fr',
    actif BOOLEAN NOT NULL DEFAULT TRUE,
    cree_le TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_assistant_chunk_actif
    ON assistant_document_chunk (actif);
CREATE INDEX IF NOT EXISTS idx_assistant_chunk_module
    ON assistant_document_chunk (module);
CREATE INDEX IF NOT EXISTS idx_assistant_chunk_fts
    ON assistant_document_chunk
    USING GIN (to_tsvector('simple', titre || ' ' || contenu));

COMMENT ON TABLE assistant_document_chunk IS
'Fragments de documents pour le RAG local. Cette table doit exister séparément dans chaque base entreprise.';
