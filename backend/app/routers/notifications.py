from datetime import datetime
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from app.db import pool_central
from app.security.auth_dependency import utilisateur_connecte

router = APIRouter(prefix="/api/notifications", tags=["notifications"])
logger = logging.getLogger(__name__)

# Même définition que database/central/008_notifications_utilisateur.sql.
# Les scripts de database/central ne s'exécutent qu'à la PREMIÈRE création de la base
# Postgres : sur une base existante la table n'existait donc pas et chaque notification
# échouait en silence. On crée la table (si absente) au démarrage et à la première utilisation.
_DDL_NOTIFICATIONS = """
CREATE TABLE IF NOT EXISTS notification_utilisateur (
    id BIGSERIAL PRIMARY KEY,
    type_compte VARCHAR(30) NOT NULL,
    utilisateur_id VARCHAR(120) NOT NULL,
    entreprise_id INTEGER REFERENCES entreprise(id) ON DELETE CASCADE,
    titre VARCHAR(180) NOT NULL,
    message VARCHAR(2000) NOT NULL,
    lien VARCHAR(500),
    categorie VARCHAR(20) NOT NULL DEFAULT 'info'
        CHECK (categorie IN ('info', 'success', 'warning', 'error')),
    cree_le TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lue_le TIMESTAMPTZ,
    CONSTRAINT notification_lien_interne CHECK (lien IS NULL OR (lien LIKE '/%' AND lien NOT LIKE '//%'))
);
CREATE INDEX IF NOT EXISTS idx_notification_utilisateur_non_lues
    ON notification_utilisateur (type_compte, utilisateur_id, entreprise_id, cree_le DESC)
    WHERE lue_le IS NULL;
CREATE INDEX IF NOT EXISTS idx_notification_utilisateur_liste
    ON notification_utilisateur (type_compte, utilisateur_id, entreprise_id, cree_le DESC, id DESC);
"""
_table_prete = False


def assurer_table() -> None:
    """Crée la table des notifications si elle n'existe pas (idempotent)."""
    global _table_prete
    if _table_prete:
        return
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(_DDL_NOTIFICATIONS)  # sans paramètres : les « % » du LIKE restent intacts
        conn.commit()
        _table_prete = True
    except Exception:
        conn.rollback()
        raise
    finally:
        pool_central.putconn(conn)


def _identite(utilisateur: dict):
    return (
        str(utilisateur.get("type") or ""),
        str(utilisateur.get("id") or ""),
        int(utilisateur.get("entrepriseId")) if utilisateur.get("entrepriseId") is not None else None,
    )


def creer_notification(type_compte: str, utilisateur_id: str, entreprise_id: int | None,
                       titre: str, message: str, lien: str | None = None,
                       categorie: str = "info") -> int:
    """Point d'entrée interne pour créer une notification depuis les modules ERP."""
    titre = (titre or "")[:180].strip()
    message = (message or "")[:2000].strip()
    if not titre or not message:
        raise ValueError("Le titre et le message sont obligatoires.")
    if categorie not in {"info", "success", "warning", "error"}:
        categorie = "info"
    if lien and (not lien.startswith("/") or lien.startswith("//")):
        lien = None

    assurer_table()
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO notification_utilisateur
                   (type_compte, utilisateur_id, entreprise_id, titre, message, lien, categorie)
                   VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (type_compte, str(utilisateur_id), entreprise_id, titre, message, lien, categorie),
            )
            identifiant = cur.fetchone()[0]
        conn.commit()
        return identifiant
    except Exception:
        conn.rollback()
        raise
    finally:
        pool_central.putconn(conn)


def notifier_action(utilisateur: dict, titre: str, message: str, lien: str,
                    categorie: str = "success") -> None:
    """Notifie l'utilisateur qui vient d'effectuer une action métier.
    Ne lève jamais d'exception : une panne de notification ne doit pas annuler l'opération."""
    try:
        creer_notification(
            type_compte=str(utilisateur.get("type") or "interne"),
            utilisateur_id=str(utilisateur.get("id") or ""),
            entreprise_id=int(utilisateur["entrepriseId"]) if utilisateur.get("entrepriseId") is not None else None,
            titre=titre, message=message, lien=lien, categorie=categorie,
        )
    except Exception:
        logger.exception("Impossible de créer la notification utilisateur")


@router.get("")
def lister_notifications(
    limit: int = Query(default=30, ge=1, le=100),
    non_lues_seulement: bool = False,
    utilisateur: dict = Depends(utilisateur_connecte),
):
    type_compte, utilisateur_id, entreprise_id = _identite(utilisateur)
    if not type_compte or not utilisateur_id:
        raise HTTPException(status_code=401, detail="Identité utilisateur incomplète.")
    conditions = ["type_compte = %s", "utilisateur_id = %s", "entreprise_id IS NOT DISTINCT FROM %s"]
    params: list = [type_compte, utilisateur_id, entreprise_id]
    if non_lues_seulement:
        conditions.append("lue_le IS NULL")
    assurer_table()
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""SELECT id, titre, message, lien, categorie, cree_le, lue_le
                    FROM notification_utilisateur WHERE {' AND '.join(conditions)}
                    ORDER BY cree_le DESC, id DESC LIMIT %s""",
                tuple(params + [limit]),
            )
            rows = cur.fetchall()
            cur.execute(
                """SELECT COUNT(*) FROM notification_utilisateur
                   WHERE type_compte = %s AND utilisateur_id = %s
                     AND entreprise_id IS NOT DISTINCT FROM %s AND lue_le IS NULL""",
                (type_compte, utilisateur_id, entreprise_id),
            )
            non_lues = cur.fetchone()[0]
    finally:
        pool_central.putconn(conn)
    return {
        "notifications": [
            {"id": r[0], "titre": r[1], "message": r[2], "lien": r[3], "categorie": r[4],
             "creeLe": r[5].isoformat() if isinstance(r[5], datetime) else r[5],
             "lueLe": r[6].isoformat() if isinstance(r[6], datetime) else r[6], "lue": r[6] is not None}
            for r in rows
        ],
        "nonLues": non_lues,
    }


@router.patch("/{notification_id}/lue")
def marquer_notification_lue(notification_id: int, utilisateur: dict = Depends(utilisateur_connecte)):
    type_compte, utilisateur_id, entreprise_id = _identite(utilisateur)
    assurer_table()
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE notification_utilisateur SET lue_le = NOW()
                   WHERE id = %s AND type_compte = %s AND utilisateur_id = %s
                     AND entreprise_id IS NOT DISTINCT FROM %s AND lue_le IS NULL""",
                (notification_id, type_compte, utilisateur_id, entreprise_id),
            )
            updated = cur.rowcount
            if not updated:
                cur.execute(
                    """SELECT 1 FROM notification_utilisateur
                       WHERE id = %s AND type_compte = %s AND utilisateur_id = %s
                         AND entreprise_id IS NOT DISTINCT FROM %s""",
                    (notification_id, type_compte, utilisateur_id, entreprise_id),
                )
                if not cur.fetchone():
                    raise HTTPException(status_code=404, detail="Notification introuvable.")
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        pool_central.putconn(conn)
    return {"message": "Notification marquée comme lue."}


@router.patch("/lire-toutes")
def marquer_toutes_lues(utilisateur: dict = Depends(utilisateur_connecte)):
    type_compte, utilisateur_id, entreprise_id = _identite(utilisateur)
    assurer_table()
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE notification_utilisateur SET lue_le = NOW()
                   WHERE type_compte = %s AND utilisateur_id = %s
                     AND entreprise_id IS NOT DISTINCT FROM %s AND lue_le IS NULL""",
                (type_compte, utilisateur_id, entreprise_id),
            )
            nombre = cur.rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool_central.putconn(conn)
    return {"message": "Notifications marquées comme lues.", "nombre": nombre}
