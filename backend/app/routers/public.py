"""Endpoints publics (sans authentification) : formulaire de la page Contact."""
import logging
import re
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.db import pool_central
from app.security.jwt_utils import exiger_super_admin

router = APIRouter(prefix="/api/public", tags=["public"])
logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS contact_public (
    id        BIGSERIAL PRIMARY KEY,
    nom       VARCHAR(150) NOT NULL,
    email     VARCHAR(200) NOT NULL,
    message   VARCHAR(3000) NOT NULL,
    ip        VARCHAR(64),
    traite    BOOLEAN NOT NULL DEFAULT FALSE,
    cree_le   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_contact_public_recent ON contact_public (traite, cree_le DESC);
"""
_table_prete = False
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
_FENETRE_S, _MAX_PAR_IP = 3600, 5
_envois: dict[str, deque] = defaultdict(deque)


class ContactPayload(BaseModel):
    nom: str = Field(min_length=2, max_length=150)
    email: str = Field(max_length=200)
    message: str = Field(min_length=5, max_length=3000)


def _assurer_table():
    global _table_prete
    if _table_prete:
        return
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(_DDL)
        conn.commit()
        _table_prete = True
    except Exception:
        conn.rollback()
        raise
    finally:
        pool_central.putconn(conn)


@router.post("/contact", status_code=201)
def envoyer_message(payload: ContactPayload, request: Request):
    if not _EMAIL.match(payload.email.strip()):
        raise HTTPException(status_code=400, detail="Adresse e-mail invalide.")
    ip = (request.client.host if request.client else "inconnue")[:64]
    maintenant = time.time()
    file = _envois[ip]
    while file and maintenant - file[0] > _FENETRE_S:
        file.popleft()
    if len(file) >= _MAX_PAR_IP:
        raise HTTPException(status_code=429, detail="Trop de messages envoyés. Réessayez plus tard.")
    file.append(maintenant)

    _assurer_table()
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO contact_public (nom, email, message, ip) VALUES (%s, %s, %s, %s)",
                (payload.nom.strip(), payload.email.strip().lower(), payload.message.strip(), ip),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool_central.putconn(conn)
    return {"message": "Message envoyé."}


@router.get("/contacts")
def lister_messages(_: dict = Depends(exiger_super_admin)):
    """Consultation par le Super Administrateur de la plateforme."""
    _assurer_table()
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, nom, email, message, traite, cree_le FROM contact_public ORDER BY cree_le DESC LIMIT 200")
            lignes = cur.fetchall()
    finally:
        pool_central.putconn(conn)
    return {"messages": [
        {"id": r[0], "nom": r[1], "email": r[2], "message": r[3], "traite": r[4], "creeLe": r[5].isoformat()}
        for r in lignes
    ]}
