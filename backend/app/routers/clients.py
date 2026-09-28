from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db import get_pool_entreprise
from app.security.permissions import exiger_permission

router = APIRouter(prefix="/api/clients", tags=["clients"])


class ClientPayload(BaseModel):
    nom: str = Field(min_length=1, max_length=150)
    email: str | None = Field(default=None, max_length=150)
    telephone: str | None = Field(default=None, max_length=30)
    adresse: str | None = None


def _pool(utilisateur):
    return get_pool_entreprise(utilisateur["nomBase"])


def _dicts(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _clean(payload: ClientPayload):
    return (
        payload.nom.strip(),
        payload.email.strip() if payload.email else None,
        payload.telephone.strip() if payload.telephone else None,
        payload.adresse.strip() if payload.adresse else None,
    )


@router.get("")
def lister_clients(utilisateur=Depends(exiger_permission("clients", "consulter"))):
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT f.id, f.nom, f.email, f.telephone, f.adresse,
                       COUNT(DISTINCT c.id) AS nombre_commandes
                FROM client f
                LEFT JOIN commande c ON c.client_id = f.id
                GROUP BY f.id, f.nom, f.email, f.telephone, f.adresse
                ORDER BY f.nom, f.id
                """
            )
            return {"clients": _dicts(cur)}
    finally:
        pool.putconn(conn)


@router.get("/{client_id}")
def obtenir_client(client_id: int, utilisateur=Depends(exiger_permission("clients", "consulter"))):
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT f.id, f.nom, f.email, f.telephone, f.adresse,
                       COUNT(DISTINCT c.id) AS nombre_commandes
                FROM client f
                LEFT JOIN commande c ON c.client_id = f.id
                WHERE f.id = %s
                GROUP BY f.id, f.nom, f.email, f.telephone, f.adresse
                """,
                (client_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Client introuvable.")
            return dict(zip([d[0] for d in cur.description], row))
    finally:
        pool.putconn(conn)


@router.post("")
def creer_client(payload: ClientPayload, utilisateur=Depends(exiger_permission("clients", "creer"))):
    values = _clean(payload)
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM client WHERE LOWER(nom) = LOWER(%s)", (values[0],))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Un client portant ce nom existe déjà.")
            cur.execute(
                """
                INSERT INTO client (nom, email, telephone, adresse)
                VALUES (%s, %s, %s, %s)
                RETURNING id, nom, email, telephone, adresse
                """,
                values,
            )
            row = cur.fetchone()
            result = dict(zip([d[0] for d in cur.description], row))
        conn.commit()
        return {"client": result, "message": "Client créé avec succès."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@router.patch("/{client_id}")
def modifier_client(client_id: int, payload: ClientPayload, utilisateur=Depends(exiger_permission("clients", "modifier"))):
    values = _clean(payload)
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM client WHERE id = %s", (client_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Client introuvable.")
            cur.execute(
                "SELECT 1 FROM client WHERE LOWER(nom) = LOWER(%s) AND id <> %s",
                (values[0], client_id),
            )
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Un autre client porte déjà ce nom.")
            cur.execute(
                """
                UPDATE client
                SET nom=%s, email=%s, telephone=%s, adresse=%s
                WHERE id=%s
                RETURNING id, nom, email, telephone, adresse
                """,
                (*values, client_id),
            )
            row = cur.fetchone()
            result = dict(zip([d[0] for d in cur.description], row))
        conn.commit()
        return {"client": result, "message": "Client modifié avec succès."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
