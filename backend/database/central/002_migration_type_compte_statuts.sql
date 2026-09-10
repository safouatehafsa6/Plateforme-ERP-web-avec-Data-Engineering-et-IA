-- Migration : à exécuter si votre base centrale a déjà été créée avec
-- l'ancienne structure (avant l'ajout du type de compte et des documents KYC).
-- Sans effet si déjà appliqué (utilise IF NOT EXISTS).

ALTER TABLE entreprise
    ADD COLUMN IF NOT EXISTS type_compte VARCHAR(20) NOT NULL DEFAULT 'entreprise';

-- Ancienne colonne statut plus large (VARCHAR(30)) -> on la réduit et on
-- met à jour les anciennes valeurs vers les 4 statuts officiels.
UPDATE entreprise SET statut = 'en_attente'
    WHERE statut IN ('inscrite', 'otp_valide', 'kyc_en_attente', 'attente_paiement', 'essai');
UPDATE entreprise SET statut = 'valide' WHERE statut = 'kyc_valide';
UPDATE entreprise SET statut = 'actif' WHERE statut = 'active';
UPDATE entreprise SET statut = 'refuse' WHERE statut IN ('kyc_rejete', 'suspendue', 'resiliee', 'expiree');

ALTER TABLE entreprise ALTER COLUMN statut TYPE VARCHAR(20);
ALTER TABLE entreprise ALTER COLUMN statut SET DEFAULT 'en_attente';

CREATE TABLE IF NOT EXISTS document_kyc (
    id              SERIAL PRIMARY KEY,
    entreprise_id   INTEGER NOT NULL REFERENCES entreprise(id) ON DELETE CASCADE,
    type_document   VARCHAR(30) NOT NULL,
    nom_fichier     VARCHAR(255) NOT NULL,
    date_soumission TIMESTAMP DEFAULT NOW()
);
