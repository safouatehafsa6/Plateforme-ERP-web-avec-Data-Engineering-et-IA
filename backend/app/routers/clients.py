from fastapi import APIRouter, Depends, HTTPException

from app.db import get_pool_entreprise
from app.schemas.clients import ClientPayload
from app.security.permissions import exiger_permission

router = APIRouter(prefix="/api/clients", tags=["clients"])


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


@router.get("/verification-doublon")
def verifier_doublons_client(
    email: str | None = None,
    telephone: str | None = None,
    exclure_id: int | None = None,
    utilisateur=Depends(exiger_permission("clients", "consulter")),
):
    """Recherche les clients partageant l'e-mail ou le téléphone saisi."""
    email_nettoye = email.strip().lower() if email and email.strip() else None
    telephone_chiffres = "".join(ch for ch in telephone or "" if ch.isdigit())
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, nom, email, telephone,
                       CASE
                         WHEN %s::text IS NOT NULL AND LOWER(TRIM(COALESCE(email, ''))) = %s THEN 'email'
                         WHEN %s <> '' AND regexp_replace(COALESCE(telephone, ''), '[^0-9]', '', 'g') = %s THEN 'telephone'
                       END AS champ
                FROM client
                WHERE (%s::text IS NOT NULL AND LOWER(TRIM(COALESCE(email, ''))) = %s)
                   OR (%s <> '' AND regexp_replace(COALESCE(telephone, ''), '[^0-9]', '', 'g') = %s)
                ORDER BY nom, id
                """,
                (email_nettoye, email_nettoye, telephone_chiffres, telephone_chiffres,
                 email_nettoye, email_nettoye, telephone_chiffres, telephone_chiffres),
            )
            rows = _dicts(cur)
            if exclure_id is not None:
                rows = [row for row in rows if row["id"] != exclure_id]
            return {"doublons": rows}
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
            cur.execute("SELECT 1 FROM client WHERE LOWER(TRIM(nom)) = LOWER(TRIM(%s))", (values[0],))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Un client portant ce nom existe déjà.")
            if values[1]:
                cur.execute("SELECT 1 FROM client WHERE LOWER(TRIM(COALESCE(email, ''))) = LOWER(TRIM(%s))", (values[1],))
                if cur.fetchone():
                    raise HTTPException(status_code=409, detail="Cette adresse e-mail est déjà utilisée par un autre client.")
            if values[2]:
                telephone_chiffres = "".join(ch for ch in values[2] if ch.isdigit())
                cur.execute("SELECT 1 FROM client WHERE regexp_replace(COALESCE(telephone, ''), '[^0-9]', '', 'g') = %s", (telephone_chiffres,))
                if cur.fetchone():
                    raise HTTPException(status_code=409, detail="Ce numéro de téléphone est déjà utilisé par un autre client.")
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
            if values[1]:
                cur.execute("SELECT 1 FROM client WHERE LOWER(TRIM(COALESCE(email, ''))) = LOWER(TRIM(%s)) AND id <> %s", (values[1], client_id))
                if cur.fetchone():
                    raise HTTPException(status_code=409, detail="Cette adresse e-mail est déjà utilisée par un autre client.")
            if values[2]:
                telephone_chiffres = "".join(ch for ch in values[2] if ch.isdigit())
                cur.execute("SELECT 1 FROM client WHERE regexp_replace(COALESCE(telephone, ''), '[^0-9]', '', 'g') = %s AND id <> %s", (telephone_chiffres, client_id))
                if cur.fetchone():
                    raise HTTPException(status_code=409, detail="Ce numéro de téléphone est déjà utilisé par un autre client.")
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
