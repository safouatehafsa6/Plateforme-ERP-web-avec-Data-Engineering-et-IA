from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db import get_pool_entreprise
from app.security.permissions import exiger_permission

router = APIRouter(prefix="/api/fournisseurs", tags=["fournisseurs"])


class FournisseurPayload(BaseModel):
    nom: str = Field(min_length=1, max_length=150)
    email: str | None = Field(default=None, max_length=150)
    telephone: str | None = Field(default=None, max_length=30)
    adresse: str | None = None


def _pool(utilisateur):
    return get_pool_entreprise(utilisateur["nomBase"])


def _dicts(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _clean(payload: FournisseurPayload):
    return (
        payload.nom.strip(),
        payload.email.strip() if payload.email else None,
        payload.telephone.strip() if payload.telephone else None,
        payload.adresse.strip() if payload.adresse else None,
    )


@router.get("")
def lister_fournisseurs(utilisateur=Depends(exiger_permission("fournisseurs", "consulter"))):
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT f.id, f.nom, f.email, f.telephone, f.adresse,
                       COUNT(DISTINCT a.id) AS nombre_achats
                FROM fournisseur f
                LEFT JOIN achat a ON a.fournisseur_id = f.id
                GROUP BY f.id, f.nom, f.email, f.telephone, f.adresse
                ORDER BY f.nom, f.id
                """
            )
            return {"fournisseurs": _dicts(cur)}
    finally:
        pool.putconn(conn)


@router.get("/{fournisseur_id}")
def obtenir_fournisseur(fournisseur_id: int, utilisateur=Depends(exiger_permission("fournisseurs", "consulter"))):
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT f.id, f.nom, f.email, f.telephone, f.adresse,
                       COUNT(DISTINCT a.id) AS nombre_achats
                FROM fournisseur f
                LEFT JOIN achat a ON a.fournisseur_id = f.id
                WHERE f.id = %s
                GROUP BY f.id, f.nom, f.email, f.telephone, f.adresse
                """,
                (fournisseur_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Fournisseur introuvable.")
            return dict(zip([d[0] for d in cur.description], row))
    finally:
        pool.putconn(conn)


@router.post("")
def creer_fournisseur(payload: FournisseurPayload, utilisateur=Depends(exiger_permission("fournisseurs", "creer"))):
    values = _clean(payload)
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM fournisseur WHERE LOWER(nom) = LOWER(%s)", (values[0],))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Un fournisseur portant ce nom existe déjà.")
            cur.execute(
                """
                INSERT INTO fournisseur (nom, email, telephone, adresse)
                VALUES (%s, %s, %s, %s)
                RETURNING id, nom, email, telephone, adresse
                """,
                values,
            )
            row = cur.fetchone()
            result = dict(zip([d[0] for d in cur.description], row))
        conn.commit()
        return {"fournisseur": result, "message": "Fournisseur créé avec succès."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@router.patch("/{fournisseur_id}")
def modifier_fournisseur(fournisseur_id: int, payload: FournisseurPayload, utilisateur=Depends(exiger_permission("fournisseurs", "modifier"))):
    values = _clean(payload)
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM fournisseur WHERE id = %s", (fournisseur_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Fournisseur introuvable.")
            cur.execute(
                "SELECT 1 FROM fournisseur WHERE LOWER(nom) = LOWER(%s) AND id <> %s",
                (values[0], fournisseur_id),
            )
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Un autre fournisseur porte déjà ce nom.")
            cur.execute(
                """
                UPDATE fournisseur
                SET nom=%s, email=%s, telephone=%s, adresse=%s
                WHERE id=%s
                RETURNING id, nom, email, telephone, adresse
                """,
                (*values, fournisseur_id),
            )
            row = cur.fetchone()
            result = dict(zip([d[0] for d in cur.description], row))
        conn.commit()
        return {"fournisseur": result, "message": "Fournisseur modifié avec succès."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
