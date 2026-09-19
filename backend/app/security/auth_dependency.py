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
    l'entreprise (gestion des collaborateurs, des rôles...).

    Ces routes travaillent toujours DANS la base d'une entreprise : elles
    exigent donc un jeton de compte d'entreprise, qui porte le nom de
    cette base (nomBase). Le Super Administrateur de la plateforme n'a
    volontairement pas accès ici : conformément au cahier des charges, il
    "n'accède jamais aux données métier des entreprises clientes" et ne
    dispose d'aucune visibilité sur leurs données internes."""
    if utilisateur.get("role") != "Admin":
        raise HTTPException(status_code=403, detail="Action réservée à l'administrateur de l'entreprise.")

    if not utilisateur.get("nomBase"):
        raise HTTPException(
            status_code=403,
            detail=(
                "Ce compte n'est rattaché à aucun environnement d'entreprise. "
                "Connectez-vous avec un compte Administrateur d'entreprise."
            ),
        )
    return utilisateur


def exiger_utilisateur_externe(utilisateur: dict = Depends(utilisateur_connecte)) -> dict:
    """A utiliser sur les routes du portail Utilisateurs externes (mes
    documents, mes factures...).

    Distinct de exiger_role_admin : ici on exige au contraire un compte
    externe (type == "externe"), jamais un collaborateur interne ni le
    Super Administrateur — l'isolation entre "gérer l'entreprise" et
    "consulter sa propre relation commerciale avec elle" doit rester
    stricte, dans les deux sens."""
    if utilisateur.get("type") != "externe" or not utilisateur.get("clientId"):
        raise HTTPException(
            status_code=403,
            detail="Ce compte n'est pas un compte du portail Utilisateurs externes.",
        )
    return utilisateur
