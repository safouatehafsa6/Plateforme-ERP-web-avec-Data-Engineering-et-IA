"""Demandes d'assistance : formulaire du bouton flottant « Assistance / Contact ».

- Chaque utilisateur crée et suit uniquement SES demandes (filtre sur type_compte + id).
- Les administrateurs de l'entreprise voient toutes les demandes et changent leur statut.
- Chaque événement crée une notification (auteur, administrateurs).
"""
import base64
import binascii
import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.db import get_pool_entreprise
from app.routers.notifications import notifier_action, creer_notification
from app.security.auth_dependency import exiger_role_admin, utilisateur_connecte

router = APIRouter(prefix="/api/support", tags=["support"])
logger = logging.getLogger(__name__)

STATUTS = ("ouverte", "en_cours", "resolue")
LIBELLES_STATUT = {"ouverte": "ouverte", "en_cours": "en cours de traitement", "resolue": "résolue"}
TAILLE_MAX_CAPTURE = 2 * 1024 * 1024  # 2 Mo
TYPES_IMAGE = {"image/png", "image/jpeg", "image/webp"}

_DDL = """
CREATE TABLE IF NOT EXISTS demande_support (
    id             SERIAL PRIMARY KEY,
    type_compte    VARCHAR(30)  NOT NULL DEFAULT 'interne',
    utilisateur_id VARCHAR(120) NOT NULL,
    auteur         VARCHAR(200),
    sujet          VARCHAR(150) NOT NULL,
    description    TEXT NOT NULL,
    page           VARCHAR(300),
    statut         VARCHAR(20)  NOT NULL DEFAULT 'ouverte',
    capture_type   VARCHAR(30),
    capture        BYTEA,
    cree_le        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    mis_a_jour_le  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT demande_support_statut_chk CHECK (statut IN ('ouverte', 'en_cours', 'resolue'))
);
CREATE INDEX IF NOT EXISTS idx_demande_support_auteur
    ON demande_support (type_compte, utilisateur_id, cree_le DESC);
CREATE INDEX IF NOT EXISTS idx_demande_support_statut
    ON demande_support (statut, cree_le DESC);
"""
_bases_pretes: set[str] = set()


class DemandePayload(BaseModel):
    sujet: str = Field(min_length=3, max_length=150)
    description: str = Field(min_length=5, max_length=4000)
    page: str | None = Field(default=None, max_length=300)
    capture: str | None = None  # data URL base64 (png, jpeg ou webp, 2 Mo max)


class StatutPayload(BaseModel):
    statut: str


def _pool(utilisateur: dict):
    nom_base = utilisateur.get("nomBase")
    if not nom_base:
        raise HTTPException(status_code=403, detail="Le support est réservé aux comptes d'une entreprise.")
    pool = get_pool_entreprise(nom_base)
    if nom_base not in _bases_pretes:
        conn = pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(_DDL)
            conn.commit()
            _bases_pretes.add(nom_base)
        except Exception:
            conn.rollback()
            raise
        finally:
            pool.putconn(conn)
    return pool


def _identite(utilisateur: dict) -> tuple[str, str]:
    return str(utilisateur.get("type") or "interne"), str(utilisateur.get("id") or "")


def _lire_capture(data_url: str | None):
    if not data_url:
        return None, None
    try:
        entete, donnees = data_url.split(",", 1)
        type_mime = entete.split(";")[0].replace("data:", "").strip().lower()
        octets = base64.b64decode(donnees, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(status_code=400, detail="Capture d'écran invalide.")
    if type_mime not in TYPES_IMAGE:
        raise HTTPException(status_code=400, detail="La capture doit être une image PNG, JPEG ou WebP.")
    if len(octets) > TAILLE_MAX_CAPTURE:
        raise HTTPException(status_code=400, detail="La capture dépasse 2 Mo.")
    return type_mime, octets


def _dicts(cur):
    colonnes = [d[0] for d in cur.description]
    return [dict(zip(colonnes, ligne)) for ligne in cur.fetchall()]


def _formater(ligne: dict) -> dict:
    return {
        "id": ligne["id"],
        "sujet": ligne["sujet"],
        "description": ligne["description"],
        "page": ligne.get("page"),
        "statut": ligne["statut"],
        "auteur": ligne.get("auteur"),
        "aCapture": bool(ligne.get("a_capture")),
        "creeLe": ligne["cree_le"].isoformat() if ligne.get("cree_le") else None,
        "misAJourLe": ligne["mis_a_jour_le"].isoformat() if ligne.get("mis_a_jour_le") else None,
    }


_COLONNES = ("id, sujet, description, page, statut, auteur, (capture IS NOT NULL) AS a_capture, "
             "cree_le, mis_a_jour_le")


@router.post("/demandes", status_code=201)
def creer_demande(payload: DemandePayload, utilisateur: dict = Depends(utilisateur_connecte)):
    type_compte, utilisateur_id = _identite(utilisateur)
    capture_type, capture = _lire_capture(payload.capture)
    auteur = (utilisateur.get("email") or "").strip() or utilisateur_id
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO demande_support
                   (type_compte, utilisateur_id, auteur, sujet, description, page, capture_type, capture)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (type_compte, utilisateur_id, auteur, payload.sujet.strip(), payload.description.strip(),
                 payload.page, capture_type, capture),
            )
            demande_id = cur.fetchone()[0]
            cur.execute(
                """SELECT u.id FROM utilisateur u JOIN role r ON r.id = u.role_id
                   WHERE r.nom = 'Admin' AND u.actif = TRUE"""
            )
            admins = [str(ligne[0]) for ligne in cur.fetchall()]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)

    notifier_action(utilisateur, "Demande d'assistance envoyée",
                    f"Votre demande n°{demande_id} « {payload.sujet.strip()} » a bien été enregistrée.", "/support")
    entreprise_id = utilisateur.get("entrepriseId")
    for admin_id in admins:
        if type_compte == "interne" and admin_id == utilisateur_id:
            continue
        try:
            creer_notification(
                type_compte="interne", utilisateur_id=admin_id,
                entreprise_id=int(entreprise_id) if entreprise_id is not None else None,
                titre="Nouvelle demande d'assistance",
                message=f"{auteur} : « {payload.sujet.strip()} » (demande n°{demande_id}).",
                lien="/support", categorie="warning",
            )
        except Exception:
            logger.exception("Notification administrateur impossible (support)")
    return {"id": demande_id, "message": "Demande envoyée."}


@router.get("/demandes")
def mes_demandes(utilisateur: dict = Depends(utilisateur_connecte)):
    type_compte, utilisateur_id = _identite(utilisateur)
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""SELECT {_COLONNES} FROM demande_support
                    WHERE type_compte = %s AND utilisateur_id = %s
                    ORDER BY cree_le DESC LIMIT 100""",
                (type_compte, utilisateur_id),
            )
            lignes = _dicts(cur)
    finally:
        pool.putconn(conn)
    return {"demandes": [_formater(l) for l in lignes]}


@router.get("/demandes/{demande_id}/capture")
def lire_capture(demande_id: int, utilisateur: dict = Depends(utilisateur_connecte)):
    type_compte, utilisateur_id = _identite(utilisateur)
    est_admin = False
    if type_compte == "interne":
        try:
            exiger_role_admin(utilisateur)
            est_admin = True
        except HTTPException:
            est_admin = False
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT capture_type, capture FROM demande_support
                   WHERE id = %s AND capture IS NOT NULL
                     AND (%s OR (type_compte = %s AND utilisateur_id = %s))""",
                (demande_id, est_admin, type_compte, utilisateur_id),
            )
            ligne = cur.fetchone()
    finally:
        pool.putconn(conn)
    if not ligne:
        raise HTTPException(status_code=404, detail="Capture introuvable.")
    return Response(content=bytes(ligne[1]), media_type=ligne[0],
                    headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"})


@router.get("/admin/demandes")
def toutes_les_demandes(statut: str | None = None, utilisateur: dict = Depends(exiger_role_admin)):
    if statut is not None and statut not in STATUTS:
        raise HTTPException(status_code=400, detail="Statut inconnu.")
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""SELECT {_COLONNES} FROM demande_support
                    WHERE (%s IS NULL OR statut = %s)
                    ORDER BY (statut = 'resolue'), cree_le DESC LIMIT 200""",
                (statut, statut),
            )
            lignes = _dicts(cur)
    finally:
        pool.putconn(conn)
    return {"demandes": [_formater(l) for l in lignes]}


@router.patch("/admin/demandes/{demande_id}")
def changer_statut(demande_id: int, payload: StatutPayload, utilisateur: dict = Depends(exiger_role_admin)):
    if payload.statut not in STATUTS:
        raise HTTPException(status_code=400, detail="Statut inconnu.")
    pool = _pool(utilisateur)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE demande_support SET statut = %s, mis_a_jour_le = NOW()
                   WHERE id = %s RETURNING type_compte, utilisateur_id, sujet""",
                (payload.statut, demande_id),
            )
            ligne = cur.fetchone()
        if not ligne:
            conn.rollback()
            raise HTTPException(status_code=404, detail="Demande introuvable.")
        conn.commit()
    except HTTPException:
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)

    type_compte, auteur_id, sujet = ligne
    entreprise_id = utilisateur.get("entrepriseId")
    try:
        creer_notification(
            type_compte=type_compte, utilisateur_id=str(auteur_id),
            entreprise_id=int(entreprise_id) if entreprise_id is not None else None,
            titre="Votre demande a évolué",
            message=f"Votre demande « {sujet} » est maintenant {LIBELLES_STATUT[payload.statut]}.",
            lien="/support", categorie="success" if payload.statut == "resolue" else "info",
        )
    except Exception:
        logger.exception("Notification de changement de statut impossible (support)")
    return {"message": "Statut mis à jour."}
