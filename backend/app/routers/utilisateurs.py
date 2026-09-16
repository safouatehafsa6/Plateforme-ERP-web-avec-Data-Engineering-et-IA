"""
utilisateurs.py — Gestion des collaborateurs internes d'une entreprise,
réservée à l'Administrateur Client (voir description des profils :
"il crée et administre l'ensemble des comptes utilisateurs de son
entreprise, attribue à chacun un identifiant unique et un mot de passe
initial, et impose le renouvellement du mot de passe dès la première
connexion").
"""

import secrets
import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db import get_pool_entreprise
from app.security.auth_dependency import exiger_role_admin

router = APIRouter(prefix="/api/utilisateurs", tags=["utilisateurs"])


class NouvelUtilisateurPayload(BaseModel):
    nom: str
    prenom: str
    email: str
    roleId: int
    departementId: int | None = None


@router.get("")
def lister_utilisateurs(utilisateur=Depends(exiger_role_admin)):
    """Liste tous les collaborateurs de l'entreprise de l'administrateur
    connecté — jamais ceux d'une autre entreprise, grâce au routage vers
    sa base dédiée (nomBase, contenu dans son jeton)."""
    pool_tenant = get_pool_entreprise(utilisateur["nomBase"])
    conn = pool_tenant.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.id, u.nom, u.prenom, u.email, u.actif, u.date_creation,
                       r.nom AS role_nom, d.nom AS departement_nom
                FROM utilisateur u
                LEFT JOIN role r ON r.id = u.role_id
                LEFT JOIN departement d ON d.id = u.departement_id
                ORDER BY u.date_creation DESC
                """
            )
            colonnes = [d[0] for d in cur.description]
            lignes = [dict(zip(colonnes, row)) for row in cur.fetchall()]
    finally:
        pool_tenant.putconn(conn)

    return {"utilisateurs": lignes}


@router.get("/roles")
def lister_roles(utilisateur=Depends(exiger_role_admin)):
    """Liste les rôles disponibles dans l'entreprise, pour peupler le
    sélecteur de rôle au moment de créer un collaborateur."""
    pool_tenant = get_pool_entreprise(utilisateur["nomBase"])
    conn = pool_tenant.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, nom, description FROM role ORDER BY nom")
            colonnes = [d[0] for d in cur.description]
            lignes = [dict(zip(colonnes, row)) for row in cur.fetchall()]
    finally:
        pool_tenant.putconn(conn)

    return {"roles": lignes}


@router.post("")
def creer_utilisateur(payload: NouvelUtilisateurPayload, utilisateur=Depends(exiger_role_admin)):
    """
    Crée un nouveau collaborateur avec un mot de passe initial généré
    aléatoirement. Le mot de passe temporaire est renvoyé UNE SEULE FOIS
    dans la réponse (jamais stocké en clair, jamais journalisé) — à
    communiquer au collaborateur, qui devra le changer à la première
    connexion (mécanisme de changement obligatoire à construire dans une
    prochaine étape).
    """
    email = payload.email.strip().lower()
    pool_tenant = get_pool_entreprise(utilisateur["nomBase"])

    mot_de_passe_temporaire = secrets.token_urlsafe(9)
    mot_de_passe_hash = bcrypt.hashpw(mot_de_passe_temporaire.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    conn = pool_tenant.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM utilisateur WHERE email = %s", (email,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Un collaborateur existe déjà avec cet email.")

            cur.execute(
                """
                INSERT INTO utilisateur (nom, prenom, email, mot_de_passe, role_id, departement_id, actif)
                VALUES (%s, %s, %s, %s, %s, %s, TRUE)
                RETURNING id
                """,
                (payload.nom, payload.prenom, email, mot_de_passe_hash, payload.roleId, payload.departementId),
            )
            nouvel_id = cur.fetchone()[0]
        conn.commit()
    finally:
        pool_tenant.putconn(conn)

    return {
        "id": nouvel_id,
        "email": email,
        "motDePasseTemporaire": mot_de_passe_temporaire,
        "message": "Collaborateur créé. Communiquez-lui ce mot de passe temporaire de façon sécurisée.",
    }
