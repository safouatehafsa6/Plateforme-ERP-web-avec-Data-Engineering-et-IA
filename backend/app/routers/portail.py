"""
portail.py — Espace personnel du portail Utilisateurs externes (voir
lettre de cadrage, section 4) : "il peut consulter en temps réel
l'ensemble de ses documents commerciaux — factures, devis et bons de
commande —, suivre l'état d'avancement de ses commandes, télécharger ses
documents au format PDF intégrant un QR Code d'authenticité, procéder au
règlement de ses factures en ligne via une passerelle de paiement
sécurisée [...]".

Isolation stricte : chaque requête est filtrée sur le client_id contenu
dans le jeton JWT de l'utilisateur externe connecté — jamais sur un
identifiant transmis par le frontend, pour qu'il soit impossible de
consulter, télécharger ou payer les documents d'un autre client en
modifiant une requête.

Paiement : ce projet ne dispose pas d'un vrai contrat avec une passerelle
de paiement (CMI, Stripe...). L'endpoint /payer SIMULE une confirmation
de paiement réussie, exactement comme le fait déjà /confirmer-paiement
lors de l'onboarding d'une entreprise (voir entreprises.py) — même
principe de mock déjà en place ailleurs dans le projet, à remplacer par
une intégration réelle avant toute mise en production.
"""

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.db import get_pool_entreprise
from app.security.auth_dependency import exiger_utilisateur_externe
from app.utils.pdf_facture import generer_pdf_facture

router = APIRouter(prefix="/api/portail", tags=["portail"])

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


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


def _recuperer_facture_du_client(pool_tenant, facture_id: int, client_id: int):
    """Vérifie que la facture existe ET appartient bien au client
    connecté, en une seule requête — c'est cette jointure qui empêche un
    client de télécharger ou payer la facture d'un autre en changeant
    juste l'identifiant dans l'URL."""
    conn = pool_tenant.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT f.id, f.numero, f.date_facture, f.montant_total, f.statut, f.code_verification, c.nom
                FROM facture f
                JOIN commande c2 ON c2.id = f.commande_id
                JOIN client c ON c.id = c2.client_id
                WHERE f.id = %s AND c2.client_id = %s
                """,
                (facture_id, client_id),
            )
            return cur.fetchone()
    finally:
        pool_tenant.putconn(conn)


@router.get("/factures/{facture_id}/pdf")
def telecharger_facture_pdf(facture_id: int, utilisateur=Depends(exiger_utilisateur_externe)):
    pool_tenant = get_pool_entreprise(utilisateur["nomBase"])
    ligne = _recuperer_facture_du_client(pool_tenant, facture_id, utilisateur["clientId"])
    if not ligne:
        raise HTTPException(status_code=404, detail="Facture introuvable.")

    _, numero, date_facture, montant_total, statut, code_verification, client_nom = ligne

    url_verification = f"{FRONTEND_URL}/verifier/{utilisateur['nomBase']}/{code_verification}"
    pdf_bytes = generer_pdf_facture(
        numero=numero,
        date_facture=date_facture,
        montant_total=montant_total,
        statut=statut,
        client_nom=client_nom,
        entreprise_nom="BENJEDDOU ERP",
        code_verification=code_verification,
        url_verification=url_verification,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="facture_{numero}.pdf"'},
    )


@router.post("/factures/{facture_id}/payer")
def payer_facture(facture_id: int, utilisateur=Depends(exiger_utilisateur_externe)):
    pool_tenant = get_pool_entreprise(utilisateur["nomBase"])
    ligne = _recuperer_facture_du_client(pool_tenant, facture_id, utilisateur["clientId"])
    if not ligne:
        raise HTTPException(status_code=404, detail="Facture introuvable.")

    _, numero, _date_facture, montant_total, statut, _code, _client_nom = ligne

    if statut == "payee":
        raise HTTPException(status_code=400, detail="Cette facture est déjà payée.")

    conn = pool_tenant.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO paiement (facture_id, date_paiement, montant, methode) VALUES (%s, %s, %s, %s)",
                (facture_id, datetime.now(timezone.utc), montant_total, "carte"),
            )
            cur.execute("UPDATE facture SET statut = 'payee' WHERE id = %s", (facture_id,))
        conn.commit()
    finally:
        pool_tenant.putconn(conn)

    return {"message": f"Paiement de la facture {numero} confirmé.", "statut": "payee"}
