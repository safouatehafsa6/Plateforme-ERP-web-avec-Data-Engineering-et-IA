"""
roles_permissions.py — Gestion des rôles et de leurs permissions,
réservée à l'Administrateur Client (moteur RBAC : "il détermine pour
chaque rôle le périmètre d'action autorisé sur l'ensemble des modules
de la plateforme, selon six niveaux de permission").
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db import get_pool_entreprise
from app.security.auth_dependency import exiger_role_admin

router = APIRouter(prefix="/api/roles", tags=["roles"])


class NouveauRolePayload(BaseModel):
    nom: str
    description: str | None = None


class PermissionsRolePayload(BaseModel):
    permissionIds: list[int]


@router.get("/permissions-disponibles")
def lister_permissions_disponibles(utilisateur=Depends(exiger_role_admin)):
    """Liste toutes les permissions existantes (module x niveau), pour
    construire la matrice de cases à cocher côté interface."""
    pool_tenant = get_pool_entreprise(utilisateur["nomBase"])
    conn = pool_tenant.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, module, action FROM permission ORDER BY module, action")
            colonnes = [d[0] for d in cur.description]
            lignes = [dict(zip(colonnes, row)) for row in cur.fetchall()]
    finally:
        pool_tenant.putconn(conn)

    return {"permissions": lignes}


@router.get("")
def lister_roles(utilisateur=Depends(exiger_role_admin)):
    """Liste les rôles de l'entreprise, chacun avec la liste des
    identifiants de permissions qui lui sont actuellement assignées."""
    pool_tenant = get_pool_entreprise(utilisateur["nomBase"])
    conn = pool_tenant.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, nom, description FROM role ORDER BY nom")
            colonnes = [d[0] for d in cur.description]
            roles = [dict(zip(colonnes, row)) for row in cur.fetchall()]

            for role in roles:
                cur.execute(
                    "SELECT permission_id FROM role_permission WHERE role_id = %s",
                    (role["id"],),
                )
                role["permissionIds"] = [r[0] for r in cur.fetchall()]
    finally:
        pool_tenant.putconn(conn)

    return {"roles": roles}


@router.post("")
def creer_role(payload: NouveauRolePayload, utilisateur=Depends(exiger_role_admin)):
    pool_tenant = get_pool_entreprise(utilisateur["nomBase"])
    conn = pool_tenant.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM role WHERE nom = %s", (payload.nom,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Un rôle avec ce nom existe déjà.")

            cur.execute(
                "INSERT INTO role (nom, description) VALUES (%s, %s) RETURNING id",
                (payload.nom, payload.description),
            )
            nouvel_id = cur.fetchone()[0]
        conn.commit()
    finally:
        pool_tenant.putconn(conn)

    return {"id": nouvel_id, "nom": payload.nom}


@router.put("/{role_id}/permissions")
def definir_permissions_role(role_id: int, payload: PermissionsRolePayload, utilisateur=Depends(exiger_role_admin)):
    """
    Remplace intégralement l'ensemble des permissions d'un rôle par celles
    envoyées — plus simple et plus fiable qu'un ajout/retrait incrémental,
    et correspond exactement à la façon dont une matrice de cases à
    cocher envoie son état (l'état complet, pas un différentiel).
    """
    pool_tenant = get_pool_entreprise(utilisateur["nomBase"])
    conn = pool_tenant.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, nom FROM role WHERE id = %s", (role_id,))
            role = cur.fetchone()
            if not role:
                raise HTTPException(status_code=404, detail="Rôle introuvable.")

            # Protection : le rôle "Admin" doit toujours conserver le
            # contrôle total, pour ne jamais se retrouver dans une
            # situation où plus personne ne peut administrer l'entreprise.
            if role[1] == "Admin":
                raise HTTPException(
                    status_code=400,
                    detail="Les permissions du rôle Admin ne peuvent pas être modifiées.",
                )

            cur.execute("DELETE FROM role_permission WHERE role_id = %s", (role_id,))
            for permission_id in payload.permissionIds:
                cur.execute(
                    "INSERT INTO role_permission (role_id, permission_id) VALUES (%s, %s)",
                    (role_id, permission_id),
                )
        conn.commit()
    finally:
        pool_tenant.putconn(conn)

    return {"message": "Permissions mises à jour.", "permissionIds": payload.permissionIds}
