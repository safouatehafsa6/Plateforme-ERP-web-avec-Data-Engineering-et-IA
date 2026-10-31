"""Compteurs d'echecs de connexion persistants (table limite_tentative).

Un compteur est « actif » pendant FENETRE_S secondes apres le dernier echec ;
au-dela il repart de zero. Si la base est indisponible, on bascule sur une
memoire locale : la protection ne disparait jamais, elle redevient seulement
non persistante le temps de la panne.
"""
import logging
import os
import threading
import time
from pathlib import Path

from app.db import pool_central

_log = logging.getLogger("tentatives")

FENETRE_S = int(os.getenv("TENTATIVES_FENETRE_S", str(15 * 60)))
FICHIER_SCHEMA = Path(__file__).resolve().parents[2] / "database" / "central" / "012_limite_tentative.sql"

_secours: dict = {}          # cle -> (echecs, derniere)
_verrou = threading.Lock()


def assurer_schema() -> None:
    """Cree la table si besoin (idempotent). Ne bloque jamais le demarrage."""
    try:
        sql = FICHIER_SCHEMA.read_text(encoding="utf-8")
        conn = pool_central.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
        finally:
            pool_central.putconn(conn)
    except Exception:
        _log.exception("Schema des tentatives non applique au demarrage")


def _secours_etat(cle: str):
    with _verrou:
        echecs, derniere = _secours.get(cle, (0, 0.0))
        if time.time() - derniere > FENETRE_S:
            _secours.pop(cle, None)
            return 0, 0
        return echecs, max(0, int(FENETRE_S - (time.time() - derniere)))


def etat(cle: str) -> tuple:
    """(echecs actifs, secondes restantes avant remise a zero)."""
    try:
        conn = pool_central.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT echecs, GREATEST(0, CEIL(EXTRACT(EPOCH FROM "
                    "(derniere + make_interval(secs => %s) - NOW())))::int) "
                    "FROM limite_tentative WHERE cle = %s AND derniere > NOW() - make_interval(secs => %s)",
                    (FENETRE_S, cle, FENETRE_S),
                )
                ligne = cur.fetchone()
        finally:
            pool_central.putconn(conn)
        return (int(ligne[0]), int(ligne[1])) if ligne else (0, 0)
    except Exception:
        _log.exception("Lecture des tentatives impossible : memoire locale utilisee")
        return _secours_etat(cle)


def ajouter(cle: str) -> int:
    """Enregistre un echec et retourne le nombre d'echecs actifs."""
    try:
        conn = pool_central.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO limite_tentative (cle, echecs, derniere) VALUES (%s, 1, NOW())
                    ON CONFLICT (cle) DO UPDATE SET
                        echecs = CASE WHEN limite_tentative.derniere < NOW() - make_interval(secs => %s)
                                      THEN 1 ELSE limite_tentative.echecs + 1 END,
                        derniere = NOW()
                    RETURNING echecs
                    """,
                    (cle, FENETRE_S),
                )
                nombre = int(cur.fetchone()[0])
                # Nettoyage opportuniste des compteurs de plus d'un jour.
                cur.execute("DELETE FROM limite_tentative WHERE derniere < NOW() - INTERVAL '1 day'")
            conn.commit()
        finally:
            pool_central.putconn(conn)
        return nombre
    except Exception:
        _log.exception("Ecriture des tentatives impossible : memoire locale utilisee")
        with _verrou:
            echecs, derniere = _secours.get(cle, (0, 0.0))
            echecs = 1 if time.time() - derniere > FENETRE_S else echecs + 1
            _secours[cle] = (echecs, time.time())
            return echecs


def reinitialiser(cle: str) -> None:
    with _verrou:
        _secours.pop(cle, None)
    try:
        conn = pool_central.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM limite_tentative WHERE cle = %s", (cle,))
            conn.commit()
        finally:
            pool_central.putconn(conn)
    except Exception:
        _log.exception("Remise a zero des tentatives impossible")
