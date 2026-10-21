-- Métadonnées des documents importés dans le RAG (une table par base entreprise).
-- Les fragments (chunks) restent dans assistant_document_chunk (013).
-- Idempotent : peut être rejoué sans risque.

CREATE TABLE IF NOT EXISTS assistant_document (
    id              TEXT PRIMARY KEY,                 -- UUID v4 généré par le backend
    titre           TEXT NOT NULL,
    nom_fichier     TEXT NOT NULL,                    -- nom d'origine (affichage uniquement)
    type_fichier    VARCHAR(10) NOT NULL,             -- 'pdf' | 'docx'
    taille_octets   BIGINT NOT NULL,
    objet_minio     TEXT NOT NULL,                    -- clé dans le bucket rag-documents
    nb_chunks       INTEGER NOT NULL DEFAULT 0,
    cree_par        INTEGER REFERENCES utilisateur(id) ON DELETE SET NULL,
    cree_le         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_assistant_document_cree_le
    ON assistant_document (cree_le DESC);
CREATE INDEX IF NOT EXISTS idx_assistant_chunk_document_id
    ON assistant_document_chunk (document_id);
