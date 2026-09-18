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


def exiger_permission(module: str, action: str):
    """
    Fabrique une dépendance FastAPI qui vérifie que le rôle de
    l'utilisateur connecté possède bien la permission (module, action)
    demandée — ferme la boucle du moteur RBAC : un rôle non-Admin sans
    cette permission précise reçoit un refus d'accès (403), même s'il
    possède un jeton JWT valide par ailleurs.

    Le rôle "Admin" garde toujours tous les droits (cohérent avec la
    règle déjà appliquée dans roles_permissions.py : ses permissions ne
    sont jamais modifiables).

    Utilisation :
        @router.delete("/utilisateurs/{id}")
        def supprimer(id: int, utilisateur=Depends(exiger_permission("utilisateurs", "suppression"))):
            ...
    """
    from app.db import get_pool_entreprise  # import différé : évite un cycle avec auth_dependency

    def verificateur(utilisateur: dict = Depends(utilisateur_connecte)) -> dict:
        if utilisateur.get("role") in ("Admin", "super_admin"):
            return utilisateur

        pool_tenant = get_pool_entreprise(utilisateur["nomBase"])
        conn = pool_tenant.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1
                    FROM role_permission rp
                    JOIN role r ON r.id = rp.role_id
                    JOIN permission p ON p.id = rp.permission_id
                    WHERE r.nom = %s AND p.module = %s AND p.action = %s
                    """,
                    (utilisateur.get("role"), module, action),
                )
                autorise = cur.fetchone() is not None
        finally:
            pool_tenant.putconn(conn)

        if not autorise:
            raise HTTPException(
                status_code=403,
                detail=f"Votre rôle ne dispose pas de la permission '{action}' sur le module '{module}'.",
            )
        return utilisateur

    return verificateur
