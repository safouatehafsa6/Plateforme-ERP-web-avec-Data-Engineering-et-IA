import os
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.db import get_pool_entreprise, pool_central
from app.security.sessions import verifier_session

_schema_bearer = HTTPBearer()


def _lire_une_ligne(pool, requete: str, parametres: tuple):
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(requete, parametres)
            return cur.fetchone()
    finally:
        pool.putconn(conn)


def utilisateur_connecte(
    identifiants: HTTPAuthorizationCredentials = Depends(_schema_bearer),
) -> dict:
    try:
        charge = jwt.decode(
            identifiants.credentials,
            os.environ["JWT_SECRET"],
            algorithms=["HS256"],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expirée, merci de vous reconnecter.")
    except (jwt.InvalidTokenError, KeyError):
        raise HTTPException(status_code=401, detail="Jeton d'authentification invalide.")

    # La signature est valide : on vérifie aussi que la session n'a pas
    # été fermée (déconnexion, révocation par l'utilisateur ou l'admin).
    verifier_session(charge)
    return charge


def exiger_role_admin(
    utilisateur: dict = Depends(utilisateur_connecte),
) -> dict:
    if (
        utilisateur.get("type") != "interne"
        or not utilisateur.get("nomBase")
        or not utilisateur.get("id")
        or not utilisateur.get("email")
    ):
        raise HTTPException(status_code=403, detail="Action réservée à l'administrateur de l'entreprise.")

    compte = _lire_une_ligne(
        get_pool_entreprise(utilisateur["nomBase"]),
        """
        SELECT u.actif, r.nom
        FROM utilisateur u
        LEFT JOIN role r ON r.id = u.role_id
        WHERE u.id = %s AND LOWER(u.email) = LOWER(%s)
        """,
        (utilisateur["id"], utilisateur["email"]),
    )

    if not compte or not compte[0]:
        raise HTTPException(status_code=401, detail="Compte inexistant ou désactivé. Reconnectez-vous.")

    if compte[1] != "Admin":
        raise HTTPException(status_code=403, detail="Action réservée à l'administrateur de l'entreprise.")

    utilisateur["role"] = compte[1]
    return utilisateur


def exiger_utilisateur_externe(
    utilisateur: dict = Depends(utilisateur_connecte),
) -> dict:
    if (
        utilisateur.get("type") != "externe"
        or not utilisateur.get("id")
        or not utilisateur.get("clientId")
        or not utilisateur.get("nomBase")
        or not utilisateur.get("email")
    ):
        raise HTTPException(status_code=403, detail="Compte du portail externe requis.")

    compte = _lire_une_ligne(
        get_pool_entreprise(utilisateur["nomBase"]),
        """
        SELECT actif, client_id
        FROM utilisateur_externe
        WHERE id = %s AND LOWER(email) = LOWER(%s)
        """,
        (utilisateur["id"], utilisateur["email"]),
    )

    if not compte or not compte[0] or str(compte[1]) != str(utilisateur["clientId"]):
        raise HTTPException(status_code=401, detail="Compte externe invalide ou désactivé.")

    return utilisateur
