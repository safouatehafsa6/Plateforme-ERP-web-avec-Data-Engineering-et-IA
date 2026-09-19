"""
utilisateurs_externes.py — Gestion des comptes du portail Utilisateurs
externes (clients/partenaires), réservée à l'Administrateur Client (voir
lettre de cadrage, section 4) : "Leurs comptes sont créés, activés et
administrés exclusivement par l'Administrateur Client, qui définit
librement l'étendue de leurs droits de consultation."

Un utilisateur externe est toujours rattaché à une fiche client. On peut
soit choisir un client déjà existant (clientId), soit en créer un nouveau
directement depuis ce formulaire (clientNom / clientEmail / clientTelephone).
"""

import secrets
import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db import get_pool_entreprise
from app.security.auth_dependency import exiger_role_admin
from app.services.provisioning import indexer_compte_central

router = APIRouter(prefix="/api/utilisateurs-externes", tags=["utilisateurs-externes"])


@router.get("")
def lister_utilisateurs_externes(utilisateur=Depends(exiger_role_admin)):
    """Liste tous les comptes externes de l'entreprise connectée, avec le
    nom du client auquel chacun est rattaché."""
    pool_tenant = get_pool_entreprise(utilisateur["nomBase"])
    conn = pool_tenant.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ue.id, ue.email, ue.actif, ue.date_creation, c.id AS client_id, c.nom AS client_nom
                FROM utilisateur_externe ue
                JOIN client c ON c.id = ue.client_id
                ORDER BY ue.date_creation DESC
                """
            )
            colonnes = [d[0] for d in cur.description]
            lignes = [dict(zip(colonnes, row)) for row in cur.fetchall()]
    finally:
        pool_tenant.putconn(conn)

    return {"utilisateursExternes": lignes}


@router.get("/clients")
def lister_clients(utilisateur=Depends(exiger_role_admin)):
    """Liste les fiches client existantes, pour choisir à qui rattacher un
    nouveau compte externe sans en recréer une en double."""
    pool_tenant = get_pool_entreprise(utilisateur["nomBase"])
    conn = pool_tenant.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, nom, email FROM client ORDER BY nom")
            colonnes = [d[0] for d in cur.description]
            lignes = [dict(zip(colonnes, row)) for row in cur.fetchall()]
    finally:
        pool_tenant.putconn(conn)

    return {"clients": lignes}


class NouvelUtilisateurExternePayload(BaseModel):
    email: str
    clientId: int | None = None
    clientNom: str | None = None
    clientEmail: str | None = None
    clientTelephone: str | None = None


@router.post("")
def creer_utilisateur_externe(payload: NouvelUtilisateurExternePayload, utilisateur=Depends(exiger_role_admin)):
    """Crée un compte externe, rattaché à un client existant (clientId) ou
    à un nouveau client créé à la volée (clientNom requis dans ce cas).

    Comme pour les collaborateurs internes, un mot de passe temporaire est
    généré et renvoyé UNE SEULE FOIS dans la réponse — à communiquer au
    client de façon sécurisée, avec renouvellement obligatoire à prévoir
    à la première connexion."""
    email = payload.email.strip().lower()

    if not payload.clientId and not payload.clientNom:
        raise HTTPException(status_code=400, detail="Choisissez un client existant ou renseignez son nom pour en créer un.")

    pool_tenant = get_pool_entreprise(utilisateur["nomBase"])
    mot_de_passe_temporaire = secrets.token_urlsafe(9)
    mot_de_passe_hash = bcrypt.hashpw(mot_de_passe_temporaire.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    conn = pool_tenant.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM utilisateur_externe WHERE email = %s", (email,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Un compte externe existe déjà avec cet email.")

            client_id = payload.clientId
            if not client_id:
                cur.execute(
                    "INSERT INTO client (nom, email, telephone) VALUES (%s, %s, %s) RETURNING id",
                    (payload.clientNom, payload.clientEmail, payload.clientTelephone),
                )
                client_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO utilisateur_externe (client_id, email, mot_de_passe, actif)
                VALUES (%s, %s, %s, TRUE)
                RETURNING id
                """,
                (client_id, email, mot_de_passe_hash),
            )
            nouvel_id = cur.fetchone()[0]
        conn.commit()
    finally:
        pool_tenant.putconn(conn)

    if "entrepriseId" in utilisateur:
        indexer_compte_central(email, utilisateur["entrepriseId"], utilisateur["nomBase"], type_compte="externe")

    return {
        "id": nouvel_id,
        "email": email,
        "motDePasseTemporaire": mot_de_passe_temporaire,
        "message": "Compte externe créé. Communiquez-lui ce mot de passe temporaire de façon sécurisée.",
    }


class ToggleActifPayload(BaseModel):
    actif: bool


@router.patch("/{utilisateur_externe_id}/actif")
def basculer_actif(utilisateur_externe_id: int, payload: ToggleActifPayload, utilisateur=Depends(exiger_role_admin)):
    """Active ou désactive un compte externe — l'Administrateur Client
    "contrôle à tout moment l'étendue de leurs droits de consultation"
    (lettre de cadrage, section 4). Un compte désactivé ne peut plus se
    connecter, mais reste visible dans la liste (traçabilité)."""
    pool_tenant = get_pool_entreprise(utilisateur["nomBase"])
    conn = pool_tenant.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE utilisateur_externe SET actif = %s WHERE id = %s RETURNING id",
                (payload.actif, utilisateur_externe_id),
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Compte externe introuvable.")
        conn.commit()
    finally:
        pool_tenant.putconn(conn)

    return {"message": "Statut mis à jour."}
