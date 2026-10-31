import os
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.db import pool_central
from app.security.sessions import verifier_session

securite = HTTPBearer()


def obtenir_utilisateur_courant(
    identifiants: HTTPAuthorizationCredentials = Depends(securite),
) -> dict:
    try:
        charge = jwt.decode(
            identifiants.credentials,
            os.environ["JWT_SECRET"],
            algorithms=["HS256"],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expirée, veuillez vous reconnecter.")
    except (jwt.InvalidTokenError, KeyError):
        raise HTTPException(status_code=401, detail="Token invalide.")

    # La signature est valide : on vérifie aussi que la session n'a pas
    # été fermée (déconnexion, révocation).
    verifier_session(charge)
    return charge


def exiger_super_admin(
    utilisateur: dict = Depends(obtenir_utilisateur_courant),
) -> dict:
    if (
        utilisateur.get("type") != "plateforme"
        or utilisateur.get("role") != "super_admin"
        or not utilisateur.get("id")
        or not utilisateur.get("email")
    ):
        raise HTTPException(status_code=403, detail="Accès réservé au Super Administrateur.")

    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM super_admin WHERE id = %s AND LOWER(email) = LOWER(%s)",
                (utilisateur["id"], utilisateur["email"]),
            )
            compte = cur.fetchone()
    finally:
        pool_central.putconn(conn)

    if not compte:
        raise HTTPException(status_code=401, detail="Compte Super Admin invalide. Reconnectez-vous.")

    return utilisateur
