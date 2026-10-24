from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import get_pool_entreprise
from app.security.auth_dependency import utilisateur_connecte
from app.security.permissions import exiger_permission
from app.services.suggestions import suggerer

router = APIRouter(prefix="/api/suggestions", tags=["suggestions"])

LIMITE_CATALOGUE = 2000


def _autorise(utilisateur: dict, module: str) -> bool:
    """Vrai si l'utilisateur peut consulter le module (mêmes règles que le reste de l'API)."""
    try:
        exiger_permission(module, "consulter")(utilisateur=dict(utilisateur))
        return True
    except HTTPException:
        return False


def _catalogue(utilisateur: dict) -> list[dict]:
    """Noms réels de l'entreprise, limités aux modules que l'utilisateur a le droit de consulter."""
    sources = [
        ("clients", "client", "SELECT nom, NULL FROM client ORDER BY nom LIMIT %s"),
        ("fournisseurs", "fournisseur", "SELECT nom, NULL FROM fournisseur ORDER BY nom LIMIT %s"),
        ("stock", "produit", "SELECT nom, reference FROM produit ORDER BY nom LIMIT %s"),
    ]
    pool = get_pool_entreprise(utilisateur["nomBase"])
    items: list[dict] = []
    for module, type_, sql in sources:
        if not _autorise(utilisateur, module):
            continue
        conn = pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (LIMITE_CATALOGUE,))
                for nom, detail in cur.fetchall():
                    items.append({"texte": nom, "type": type_, "detail": detail or ""})
        finally:
            pool.putconn(conn)
    return items


@router.get("")
def suggestions(
    q: str = Query(..., max_length=200),
    langue: str = Query("fr", pattern="^(fr|en|ar)$"),
    module: str | None = Query(None, max_length=50),
    limite: int = Query(6, ge=1, le=10),
    utilisateur=Depends(utilisateur_connecte),
):
    """Suggestions pendant la frappe : glossaire métier + noms réels (selon les permissions)."""
    catalogue = _catalogue(utilisateur) if utilisateur.get("type") == "interne" and utilisateur.get("nomBase") else []
    return {"suggestions": suggerer(q, catalogue, langue=langue, module=module, limite=limite)}
