-- 010_code_verification_facture.sql
-- Migration a executer sur CHAQUE base entreprise.
--
-- Ajoute a chaque facture un code d'authenticite unique et imprevisible,
-- destine a etre encode dans un QR code sur le PDF telecharge depuis le
-- portail Utilisateurs externes. Ce code permet a QUICONQUE scanne le
-- QR (sans etre connecte) de verifier que le document est authentique,
-- via une route publique de verification.
--
-- Le code n'est jamais devinable (32 caracteres aleatoires) : il ne
-- revele rien sur le numero de facture ou l'identite du client.

-- gen_random_bytes vient de l'extension pgcrypto ; on l'active en premier
-- (sans erreur si deja presente), avant de generer les codes.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE facture
    ADD COLUMN IF NOT EXISTS code_verification VARCHAR(64) UNIQUE;

-- Renseigne un code pour les factures deja existantes qui n'en ont pas
-- encore (ex-tables de test creees avant cette migration).
UPDATE facture
SET code_verification = encode(gen_random_bytes(24), 'hex')
WHERE code_verification IS NULL;

-- Colonne de reserve pour mettre en cache le QR code lui-meme (ex: en
-- base64 ou en URL d'image), si on veut un jour eviter de le regenerer
-- a chaque telechargement de PDF. A ce jour, generer_pdf_facture()
-- (backend/app/utils/pdf_facture.py) reconstruit le QR a la volee a
-- partir de code_verification et ne lit/n'ecrit PAS encore cette
-- colonne — elle est ajoutee ici uniquement pour que le schema soit
-- identique sur toutes les bases entreprise, en prevision de cette
-- optimisation future.
ALTER TABLE facture
    ADD COLUMN IF NOT EXISTS qr_code TEXT;
