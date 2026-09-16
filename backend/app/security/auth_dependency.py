"""
auth_dependency.py — Vérifie le jeton JWT envoyé par le frontend (en-tête
Authorization: Bearer ...) et fournit l'identité de l'utilisateur connecté
(email, rôle, base entreprise) aux routes qui en ont besoin.

Utilisation dans une route :

    @router.get("/utilisateurs")
    def lister(utilisateur=Depends(utilisateur_connecte)):
        ...
"""

import os
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

_schema_bearer = HTTPBearer()


def utilisateur_connecte(identifiants: HTTPAuthorizationCredentials = Depends(_schema_bearer)) -> dict:
    token = identifiants.credentials
    try:
        payload = jwt.decode(
            token,
            os.getenv("JWT_SECRET", "dev_secret_a_remplacer"),
            algorithms=["HS256"],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expirée, merci de vous reconnecter.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Jeton d'authentification invalide.")

    return payload  # contient : id, email, role, nomBase (si compte tenant)


def exiger_role_admin(utilisateur: dict = Depends(utilisateur_connecte)) -> dict:
    """A utiliser sur les routes réservées à l'Administrateur de
    l'entreprise (gestion des collaborateurs, des rôles...)."""
    if utilisateur.get("role") not in ("Admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Action réservée à l'administrateur de l'entreprise.")
    return utilisateur
