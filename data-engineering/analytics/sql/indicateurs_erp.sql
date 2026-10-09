SELECT
    COUNT(*) AS nombre_commandes,
    COALESCE(SUM(montant_total), 0) AS montant_total
FROM commande;

SELECT
    COUNT(*) AS nombre_factures,
    COALESCE(SUM(montant_total), 0) AS montant_total
FROM facture;

SELECT
    COUNT(*) AS nombre_achats,
    COALESCE(SUM(montant_total), 0) AS montant_total
FROM achat;

SELECT COUNT(*) AS nombre_clients
FROM client;

SELECT COUNT(*) AS nombre_fournisseurs
FROM fournisseur;

SELECT
    statut,
    COUNT(*) AS nombre_commandes,
    COALESCE(SUM(montant_total), 0) AS montant_total
FROM commande
GROUP BY statut
ORDER BY nombre_commandes DESC;

SELECT
    DATE_TRUNC('month', date_commande) AS mois,
    COUNT(*) AS nombre_commandes,
    COALESCE(SUM(montant_total), 0) AS montant_total
FROM commande
GROUP BY DATE_TRUNC('month', date_commande)
ORDER BY mois;

SELECT
    statut,
    COUNT(*) AS nombre_achats,
    COALESCE(SUM(montant_total), 0) AS montant_total
FROM achat
GROUP BY statut
ORDER BY nombre_achats DESC;
