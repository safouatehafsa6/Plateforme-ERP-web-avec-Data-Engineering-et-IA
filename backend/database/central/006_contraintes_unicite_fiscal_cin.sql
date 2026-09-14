-- Migration : contraintes d'unicité strictes au niveau base de données
-- pour le numéro fiscal et le numéro de CIN (défense en profondeur, en
-- plus de la vérification déjà faite côté applicatif) — conformément à
-- la demande explicite de garantir l'unicité "au niveau du backend ET de
-- la base de données".
--
-- Un index unique partiel est utilisé (au lieu d'une contrainte UNIQUE
-- classique) car ces deux champs sont optionnels selon le type de compte :
-- une contrainte UNIQUE classique en PostgreSQL autorise déjà plusieurs
-- valeurs NULL, donc cela fonctionne nativement pour les personnes
-- physiques (sans numéro fiscal).

CREATE UNIQUE INDEX IF NOT EXISTS idx_entreprise_numero_fiscal_unique
    ON entreprise (numero_fiscal)
    WHERE numero_fiscal IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_entreprise_numero_cin_unique
    ON entreprise (numero_cin)
    WHERE numero_cin IS NOT NULL;
