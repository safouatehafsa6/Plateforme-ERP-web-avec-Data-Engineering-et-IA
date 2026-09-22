"""
verification.py — Route PUBLIQUE (aucune authentification) permettant de
vérifier l'authenticité d'un document via le QR code imprimé sur son PDF
(lettre de cadrage, section 4).

Volontairement accessible sans compte : c'est tout l'intérêt d'un QR
code d'authenticité, qu'un tiers (comptable, contrôleur...) doit pouvoir
scanner et vérifier sans avoir à se connecter au portail.

Ne renvoie que des informations minimales, non sensibles (numéro, date,
montant, statut, nom de l'entreprise émettrice) — jamais les autres
documents du client, ni aucune donnée interne de l'entreprise.
"""

from fastapi import APIRouter, HTTPException

from app.db import pool_central, get_pool_entreprise

router = APIRouter(prefix="/api/verifier", tags=["verification"])


@router.get("/{nom_base}/{code_verification}")
def verifier_document(nom_base: str, code_verification: str):
    # On confirme d'abord que nom_base correspond bien à une entreprise
    # réelle de la plateforme, pour ne jamais exécuter une requête sur un
    # nom de base arbitraire fourni dans l'URL.
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT nom FROM entreprise WHERE nom_base = %s", (nom_base,))
            ligne_entreprise = cur.fetchone()
    finally:
        pool_central.putconn(conn)

    if not ligne_entreprise:
        raise HTTPException(status_code=404, detail="Document introuvable ou invalide.")

    entreprise_nom = ligne_entreprise[0]

    pool_tenant = get_pool_entreprise(nom_base)
    conn = pool_tenant.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT numero, date_facture, montant_total, statut FROM facture WHERE code_verification = %s",
                (code_verification,),
            )
            ligne = cur.fetchone()
    finally:
        pool_tenant.putconn(conn)

    if not ligne:
        raise HTTPException(status_code=404, detail="Document introuvable ou invalide.")

    numero, date_facture, montant_total, statut = ligne
    return {
        "authentique": True,
        "entreprise": entreprise_nom,
        "numero": numero,
        "dateFacture": date_facture,
        "montantTotal": montant_total,
        "statut": statut,
    }
