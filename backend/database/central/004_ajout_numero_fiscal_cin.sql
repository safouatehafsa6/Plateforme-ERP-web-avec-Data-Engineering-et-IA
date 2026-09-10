-- Migration : ajout des champs numéro fiscal et CIN, explicitement
-- demandés en texte (en plus du document justificatif déjà collecté en
-- KYC) — voir demande de l'entreprise, section 2.

ALTER TABLE entreprise
    ADD COLUMN IF NOT EXISTS numero_fiscal VARCHAR(50),
    ADD COLUMN IF NOT EXISTS numero_cin VARCHAR(50);
