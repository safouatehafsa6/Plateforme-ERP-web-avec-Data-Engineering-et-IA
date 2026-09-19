"""
portail.py — Espace personnel du portail Utilisateurs externes (voir
lettre de cadrage, section 4) : "il peut consulter en temps réel
l'ensemble de ses documents commerciaux — factures, devis et bons de
commande —, suivre l'état d'avancement de ses commandes [...]".

Isolation stricte : chaque requête est filtrée sur le client_id contenu
dans le jeton JWT de l'utilisateur externe connecté — jamais sur un
identifiant transmis par le frontend, pour qu'il soit impossible de
consulter les documents d'un autre client en modifiant une requête.

Le téléchargement PDF avec QR code d'authenticité et le paiement en ligne
(mentionnés dans la lettre de cadrage) ne sont pas encore implémentés ici
— cette première étape couvre la consultation de l'espace personnel.
"""

from fastapi import APIRouter, Depends

from app.db import get_pool_entreprise
from app.security.auth_dependency import exiger_utilisateur_externe

router = APIRouter(prefix="/api/portail", tags=["portail"])


@router.get("/moi")
def mon_profil(utilisateur=Depends(exiger_utilisateur_externe)):
    """Identité du client connecté, pour l'en-tête du portail."""
    pool_tenant = get_pool_entreprise(utilisateur["nomBase"])
    conn = pool_tenant.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT nom, email, telephone, adresse FROM client WHERE id = %s",
                (utilisateur["clientId"],),
            )
            ligne = cur.fetchone()
    finally:
        pool_tenant.putconn(conn)

    if not ligne:
        return {"nom": None, "email": None, "telephone": None, "adresse": None}

    nom, email, telephone, adresse = ligne
    return {"nom": nom, "email": email, "telephone": telephone, "adresse": adresse}


@router.get("/mes-documents")
def mes_documents(utilisateur=Depends(exiger_utilisateur_externe)):
    """Commandes (dont les devis, qui sont des commandes au statut
    'devis') et factures du client connecté — jamais celles d'un autre
    client, ni aucune autre donnée interne de l'entreprise."""
    client_id = utilisateur["clientId"]
    pool_tenant = get_pool_entreprise(utilisateur["nomBase"])
    conn = pool_tenant.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, date_commande, statut, montant_total
                FROM commande
                WHERE client_id = %s
                ORDER BY date_commande DESC
                """,
                (client_id,),
            )
            colonnes = [d[0] for d in cur.description]
            commandes = [dict(zip(colonnes, row)) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT f.id, f.numero, f.date_facture, f.montant_total, f.statut
                FROM facture f
                JOIN commande c ON c.id = f.commande_id
                WHERE c.client_id = %s
                ORDER BY f.date_facture DESC
                """,
                (client_id,),
            )
            colonnes = [d[0] for d in cur.description]
            factures = [dict(zip(colonnes, row)) for row in cur.fetchall()]
    finally:
        pool_tenant.putconn(conn)

    return {"commandes": commandes, "factures": factures}
