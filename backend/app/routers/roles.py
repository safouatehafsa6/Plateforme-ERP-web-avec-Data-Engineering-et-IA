"""
roles.py — Gestion des rôles et de leurs permissions (moteur RBAC), réservée
à l'Administrateur Client : "il détermine pour chaque rôle le périmètre
d'action autorisé sur l'ensemble des modules de la plateforme, selon six
niveaux de permission : consultation, création, modification, suppression,
validation et export. Ces paramètres peuvent être ajustés à tout moment."
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db import get_pool_entreprise
from app.security.auth_dependency import exiger_role_admin

router = APIRouter(prefix="/api/roles", tags=["roles"])

ACTIONS_VALIDES = ["consulter", "creer", "modifier", "supprimer", "valider", "exporter"]


@router.get("")
def lister_roles(utilisateur=Depends(exiger_role_admin)):
    pool_tenant = get_pool_entreprise(utilisateur["nomBase"])
    conn = pool_tenant.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT r.id, r.nom, r.description, COUNT(u.id) AS nb_utilisateurs
                FROM role r
                LEFT JOIN utilisateur u ON u.role_id = r.id
                GROUP BY r.id, r.nom, r.description
                ORDER BY r.nom
            """)
            colonnes = [d[0] for d in cur.description]
            lignes = [dict(zip(colonnes, row)) for row in cur.fetchall()]
    finally:
        pool_tenant.putconn(conn)
    return {"roles": lignes}


class NouveauRolePayload(BaseModel):
    nom: str
    description: str | None = None


@router.post("")
def creer_role(payload: NouveauRolePayload, utilisateur=Depends(exiger_role_admin)):
    pool_tenant = get_pool_entreprise(utilisateur["nomBase"])
    conn = pool_tenant.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM role WHERE nom = %s", (payload.nom,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Un rôle porte déjà ce nom.")
            cur.execute(
                "INSERT INTO role (nom, description) VALUES (%s, %s) RETURNING id",
                (payload.nom, payload.description),
            )
            nouvel_id = cur.fetchone()[0]
        conn.commit()
    finally:
        pool_tenant.putconn(conn)
    return {"id": nouvel_id, "message": "Rôle créé."}


@router.delete("/{role_id}")
def supprimer_role(role_id: int, utilisateur=Depends(exiger_role_admin)):
    pool_tenant = get_pool_entreprise(utilisateur["nomBase"])
    conn = pool_tenant.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT nom FROM role WHERE id = %s", (role_id,))
            ligne = cur.fetchone()
            if not ligne:
                raise HTTPException(status_code=404, detail="Rôle introuvable.")
            if ligne[0] == "Admin":
                raise HTTPException(status_code=400, detail="Le rôle Admin ne peut pas être supprimé.")
            cur.execute("SELECT COUNT(*) FROM utilisateur WHERE role_id = %s", (role_id,))
            if cur.fetchone()[0] > 0:
                raise HTTPException(status_code=400, detail="Ce rôle est encore attribué à des collaborateurs.")
            cur.execute("DELETE FROM role WHERE id = %s", (role_id,))
        conn.commit()
    finally:
        pool_tenant.putconn(conn)
    return {"message": "Rôle supprimé."}


@router.get("/{role_id}/permissions")
def obtenir_matrice_permissions(role_id: int, utilisateur=Depends(exiger_role_admin)):
    """Retourne tous les modules × 6 actions, avec un booléen indiquant si
    ce rôle possède chaque permission — prêt à afficher comme une matrice
    de cases à cocher côté frontend."""
    pool_tenant = get_pool_entreprise(utilisateur["nomBase"])
    conn = pool_tenant.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, module, action FROM permission ORDER BY module, action")
            toutes = [{"id": r[0], "module": r[1], "action": r[2]} for r in cur.fetchall()]

            cur.execute("SELECT permission_id FROM role_permission WHERE role_id = %s", (role_id,))
            accordees = {r[0] for r in cur.fetchall()}
    finally:
        pool_tenant.putconn(conn)

    for p in toutes:
        p["accordee"] = p["id"] in accordees

    modules = sorted({p["module"] for p in toutes})
    return {"modules": modules, "actions": ACTIONS_VALIDES, "permissions": toutes}


class MatricePermissionsPayload(BaseModel):
    permissionIds: list[int]  # liste complète des permissions accordées (remplace l'existant)


@router.put("/{role_id}/permissions")
def mettre_a_jour_permissions(role_id: int, payload: MatricePermissionsPayload, utilisateur=Depends(exiger_role_admin)):
    pool_tenant = get_pool_entreprise(utilisateur["nomBase"])
    conn = pool_tenant.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT nom FROM role WHERE id = %s", (role_id,))
            ligne = cur.fetchone()
            if not ligne:
                raise HTTPException(status_code=404, detail="Rôle introuvable.")

            cur.execute("DELETE FROM role_permission WHERE role_id = %s", (role_id,))
            if payload.permissionIds:
                cur.executemany(
                    "INSERT INTO role_permission (role_id, permission_id) VALUES (%s, %s)",
                    [(role_id, pid) for pid in payload.permissionIds],
                )
        conn.commit()
    finally:
        pool_tenant.putconn(conn)

    return {"message": "Permissions mises à jour."}
