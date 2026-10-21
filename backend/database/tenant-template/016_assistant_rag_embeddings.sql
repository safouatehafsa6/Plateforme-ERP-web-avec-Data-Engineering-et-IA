-- Embeddings pour recherche sémantique locale (JSONB évite d'imposer pgvector).
-- Les vecteurs sont calculés dans le backend avec FastEmbed, puis comparés localement.
ALTER TABLE assistant_document_chunk
    ADD COLUMN IF NOT EXISTS embedding JSONB,
    ADD COLUMN IF NOT EXISTS embedding_model TEXT;

CREATE INDEX IF NOT EXISTS idx_assistant_chunk_embedding_pending
    ON assistant_document_chunk (actif)
    WHERE embedding IS NULL;
