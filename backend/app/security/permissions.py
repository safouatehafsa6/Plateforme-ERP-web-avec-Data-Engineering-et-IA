from fastapi import Depends, HTTPException

from app.db import get_pool_entreprise
from app.security.auth_dependency import utilisateur_connecte


def exiger_permission(module: str, action: str):
    """Dépendance RBAC pour les modules métier d'une entreprise."""
    def verifier(utilisateur: dict = Depends(utilisateur_connecte)) -> dict:
        nom_base = utilisateur.get("nomBase")
        if not nom_base or utilisateur.get("type") == "externe":
            raise HTTPException(status_code=403, detail="Accès réservé aux collaborateurs de l'entreprise.")

        if utilisateur.get("role") == "Admin":
            return utilisateur

        utilisateur_id = utilisateur.get("id")
        if not utilisateur_id:
            raise HTTPException(status_code=403, detail="Utilisateur d'entreprise invalide.")

        pool_tenant = get_pool_entreprise(nom_base)
        conn = pool_tenant.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1
                    FROM utilisateur u
                    JOIN role_permission rp ON rp.role_id = u.role_id
                    JOIN permission p ON p.id = rp.permission_id
                    WHERE u.id = %s AND u.actif = TRUE
                      AND p.module = %s AND p.action = %s
                    LIMIT 1
                    """,
                    (utilisateur_id, module, action),
                )
                autorise = cur.fetchone() is not None
        finally:
            pool_tenant.putconn(conn)

        if not autorise:
            raise HTTPException(status_code=403, detail=f"Permission requise : {module}.{action}.")
        return utilisateur

    return verifier
