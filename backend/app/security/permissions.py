from fastapi import Depends, HTTPException

from app.db import get_pool_entreprise
from app.security.auth_dependency import utilisateur_connecte


def exiger_permission(module: str, action: str):
    """Verifie le compte actif et ses permissions actuelles en base."""

    def verifier(utilisateur: dict = Depends(utilisateur_connecte)) -> dict:
        nom_base = utilisateur.get("nomBase")
        type_compte = utilisateur.get("type")
        utilisateur_id = utilisateur.get("id")

        if not nom_base or type_compte != "interne" or not utilisateur_id:
            raise HTTPException(
                status_code=403,
                detail="Acces reserve aux collaborateurs de l'entreprise.",
            )

        pool = get_pool_entreprise(nom_base)
        conn = pool.getconn()

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT u.actif, r.nom,
                           EXISTS (
                               SELECT 1
                               FROM role_permission rp
                               JOIN permission p ON p.id = rp.permission_id
                               WHERE rp.role_id = u.role_id
                                 AND p.module = %s
                                 AND p.action = %s
                           ) AS autorise
                    FROM utilisateur u
                    LEFT JOIN role r ON r.id = u.role_id
                    WHERE u.id = %s
                    """,
                    (module, action, utilisateur_id),
                )
                compte = cur.fetchone()
        finally:
            pool.putconn(conn)

        if not compte or not compte[0]:
            raise HTTPException(
                status_code=401,
                detail="Compte inexistant ou desactive. Reconnectez-vous.",
            )

        role_actuel = compte[1]
        autorise = compte[2]

        if role_actuel == "Admin":
            utilisateur["role"] = role_actuel
            return utilisateur

        if not autorise:
            raise HTTPException(
                status_code=403,
                detail=f"Permission requise : {module}.{action}.",
            )

        utilisateur["role"] = role_actuel
        return utilisateur

    return verifier


ACTIONS_RBAC = ("consulter", "creer", "modifier", "supprimer", "valider", "exporter")


def actions_autorisees(utilisateur: dict, module: str) -> list[str]:
    """Actions RBAC dont dispose le compte sur un module (sert à adapter l'interface ;
    chaque route reste protégée par exiger_permission)."""
    pool = get_pool_entreprise(utilisateur["nomBase"])
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.nom, COALESCE(array_agg(p.action) FILTER (WHERE p.action IS NOT NULL), '{}')
                FROM utilisateur u
                LEFT JOIN role r ON r.id = u.role_id
                LEFT JOIN role_permission rp ON rp.role_id = u.role_id
                LEFT JOIN permission p ON p.id = rp.permission_id AND p.module = %s
                WHERE u.id = %s AND u.actif
                GROUP BY r.nom
                """,
                (module, utilisateur["id"]),
            )
            ligne = cur.fetchone()
    finally:
        pool.putconn(conn)
    if not ligne:
        return []
    if ligne[0] == "Admin":
        return list(ACTIONS_RBAC)
    return [a for a in ACTIONS_RBAC if a in (ligne[1] or [])]
