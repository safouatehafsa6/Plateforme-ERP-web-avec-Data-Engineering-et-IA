"""Persistance Room Live (PostgreSQL).

Où sont stockées les données :
  - collaborateur d'une entreprise  -> base de SON entreprise (jeton avec nomBase) ;
  - Super Admin (aucune base entreprise) -> base centrale.
L'isolation multi-tenant est donc physique : une requête ne peut pas lire la base d'une autre
entreprise, puisque la connexion est ouverte sur la base du jeton.

Politique d'erreur :
  - salles / participants / invitations / messages : écriture « best effort » (journalisée) pour
    qu'une panne de base ne coupe jamais une réunion en cours ;
  - enregistrements : erreurs remontées (l'appelant répond 503), car on ne doit jamais prétendre
    avoir enregistré ce qui ne l'est pas.
"""
from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from psycopg2.errors import UniqueViolation

from app.db import get_pool_entreprise, pool_central

log = logging.getLogger("erp.room_store")

_DOSSIER = Path(__file__).resolve().parents[2] / "database"
_SCRIPT_TENANT = _DOSSIER / "tenant-template" / "021_room_live.sql"
_SCRIPT_CENTRAL = _DOSSIER / "central" / "016_room_live.sql"

_prets: set = set()
_verrou = threading.Lock()


class RecordingConflict(Exception):
    """Un enregistrement est déjà en cours dans cette salle."""


def db_key(user: dict) -> str | None:
    """Clé de base : nom de la base entreprise, ou None pour la base centrale."""
    return user.get("nomBase") or None


def _pool(key: str | None):
    return pool_central if key is None else get_pool_entreprise(key)


def _assurer_schema(key: str | None, conn) -> None:
    """Crée les tables sur une base existante (une seule fois par processus) et marque
    « interrompus » les enregistrements restés « en_cours » (aucun ne peut survivre à un
    redémarrage du serveur, puisque le flux vient du navigateur de l'hôte)."""
    with _verrou:
        if key in _prets:
            return
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('room_live_salle') IS NOT NULL "
                        "AND to_regclass('room_live_enregistrement_journal') IS NOT NULL")
            if not cur.fetchone()[0]:
                script = _SCRIPT_CENTRAL if key is None else _SCRIPT_TENANT
                cur.execute(script.read_text(encoding="utf-8"))
            cur.execute("UPDATE room_live_enregistrement SET statut = 'interrompu', termine_le = NOW() "
                        "WHERE statut = 'en_cours'")
        conn.commit()
        _prets.add(key)


@contextmanager
def _tx(key: str | None):
    pool = _pool(key)
    conn = pool.getconn()
    try:
        _assurer_schema(key, conn)
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def _best_effort(fonction):
    def enveloppe(*args, **kwargs):
        try:
            return fonction(*args, **kwargs)
        except Exception:
            log.exception("Persistance Room Live impossible (%s)", fonction.__name__)
            return None
    enveloppe.__name__ = fonction.__name__
    return enveloppe


def _dt(valeur) -> datetime:
    if isinstance(valeur, datetime):
        return valeur if valeur.tzinfo else valeur.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(valeur)


# --------------------------------------------------------------------------- salles

@_best_effort
def enregistrer_salle(room: dict) -> None:
    with _tx(room["db"]) as cur:
        cur.execute(
            """INSERT INTO room_live_salle (id, nom, description, privee, proprietaire_id, proprietaire_email, cree_le)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET nom = EXCLUDED.nom, description = EXCLUDED.description,
                   privee = EXCLUDED.privee, proprietaire_id = EXCLUDED.proprietaire_id,
                   proprietaire_email = EXCLUDED.proprietaire_email""",
            (room["id"], room["name"], room["description"], room["is_private"],
             room["owner_id"], room["owner_email"], _dt(room["created_at"])),
        )
        for p in room["participants"].values():
            _upsert_participant(cur, room["id"], p)


def _upsert_participant(cur, room_id: str, p: dict) -> None:
    cur.execute(
        """INSERT INTO room_live_participant (salle_id, user_id, email, role, rejoint_le, bloque)
           VALUES (%s, %s, %s, %s, %s, %s)
           ON CONFLICT (salle_id, user_id) DO UPDATE SET email = EXCLUDED.email, role = EXCLUDED.role,
               bloque = EXCLUDED.bloque""",
        (room_id, p["user_id"], p.get("email"), p.get("role", "member"),
         _dt(p.get("joined_at") or datetime.now(timezone.utc)), bool(p.get("blocked"))),
    )


@_best_effort
def enregistrer_participant(room: dict, participant: dict) -> None:
    with _tx(room["db"]) as cur:
        _upsert_participant(cur, room["id"], participant)


@_best_effort
def retirer_participant(room: dict, user_id: str) -> None:
    with _tx(room["db"]) as cur:
        cur.execute("DELETE FROM room_live_participant WHERE salle_id = %s AND user_id = %s",
                    (room["id"], user_id))


@_best_effort
def enregistrer_proprietaire(room: dict) -> None:
    with _tx(room["db"]) as cur:
        cur.execute("UPDATE room_live_salle SET proprietaire_id = %s, proprietaire_email = %s WHERE id = %s",
                    (room["owner_id"], room["owner_email"], room["id"]))
        for p in room["participants"].values():
            _upsert_participant(cur, room["id"], p)


@_best_effort
def enregistrer_invitation(room: dict, email: str, expire: datetime) -> None:
    with _tx(room["db"]) as cur:
        cur.execute(
            """INSERT INTO room_live_invitation (salle_id, email, expire_le) VALUES (%s, %s, %s)
               ON CONFLICT (salle_id, email) DO UPDATE SET expire_le = EXCLUDED.expire_le""",
            (room["id"], email, expire),
        )


@_best_effort
def supprimer_invitation(room: dict, email: str) -> None:
    with _tx(room["db"]) as cur:
        cur.execute("DELETE FROM room_live_invitation WHERE salle_id = %s AND email = %s", (room["id"], email))


@_best_effort
def enregistrer_message(room: dict, message: dict) -> None:
    with _tx(room["db"]) as cur:
        cur.execute(
            """INSERT INTO room_live_message (id, salle_id, expediteur_id, expediteur, contenu, cree_le)
               VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING""",
            (message["id"], room["id"], message["sender_id"], message.get("sender"),
             message["content"], _dt(message["created_at"])),
        )


@_best_effort
def fermer_salle(key: str | None, room_id: str) -> None:
    with _tx(key) as cur:
        cur.execute("UPDATE room_live_salle SET fermee_le = NOW() WHERE id = %s AND fermee_le IS NULL", (room_id,))


def charger_salles(key: str | None, tenant: str) -> dict[str, dict] | None:
    """Recharge les salles ouvertes d'une base (participants, invitations, 200 derniers messages).
    Renvoie None en cas d'erreur (l'appelant réessaiera au prochain accès)."""
    salles: dict[str, dict] = {}
    try:
        with _tx(key) as cur:
            cur.execute("SELECT id, nom, description, privee, proprietaire_id, proprietaire_email, cree_le "
                        "FROM room_live_salle WHERE fermee_le IS NULL")
            for sid, nom, desc, privee, oid, oemail, cree in cur.fetchall():
                salles[sid] = {
                    "id": sid, "name": nom, "description": desc, "is_private": privee, "tenant": tenant,
                    "db": key, "owner_id": oid, "owner_email": oemail, "created_at": cree.isoformat(),
                    "invited_emails": set(), "invite_expiry": {}, "last_summary": None,
                    "participants": {}, "messages": [],
                }
            if not salles:
                return salles
            ids = list(salles)
            cur.execute("SELECT salle_id, user_id, email, role, rejoint_le, bloque "
                        "FROM room_live_participant WHERE salle_id = ANY(%s) ORDER BY rejoint_le", (ids,))
            for sid, uid, email, role, rejoint, bloque in cur.fetchall():
                salles[sid]["participants"][uid] = {
                    "user_id": uid, "email": email, "role": role,
                    "joined_at": rejoint.isoformat(), "blocked": bloque,
                }
            cur.execute("SELECT salle_id, email, expire_le FROM room_live_invitation "
                        "WHERE salle_id = ANY(%s) AND expire_le > NOW()", (ids,))
            for sid, email, expire in cur.fetchall():
                salles[sid]["invited_emails"].add(email)
                salles[sid]["invite_expiry"][email] = expire
            cur.execute(
                """SELECT salle_id, id, expediteur_id, expediteur, contenu, cree_le FROM (
                       SELECT m.*, ROW_NUMBER() OVER (PARTITION BY salle_id ORDER BY cree_le DESC) AS rang
                       FROM room_live_message m WHERE salle_id = ANY(%s)) t
                   WHERE rang <= 200 ORDER BY cree_le""", (ids,))
            for sid, mid, eid, exp, contenu, cree in cur.fetchall():
                salles[sid]["messages"].append({
                    "id": mid, "content": contenu, "sender_id": eid, "sender": exp,
                    "created_at": cree.isoformat(),
                })
    except Exception:
        log.exception("Rechargement des salles Room Live impossible")
        return None
    return salles


# ------------------------------------------------------------------- enregistrements

def creer_enregistrement(room: dict, user: dict, rec_id: str, mime: str, chemin: str,
                         retention_jours: int) -> dict:
    retention = datetime.now(timezone.utc) + timedelta(days=retention_jours)
    try:
        with _tx(room["db"]) as cur:
            cur.execute(
                """INSERT INTO room_live_enregistrement
                       (id, salle_id, salle_nom, proprietaire_id, demarre_par_id, demarre_par_email,
                        mime, chemin, retention_jusqu_au)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (rec_id, room["id"], room["name"], room["owner_id"], str(user.get("id") or user.get("sub")),
                 user.get("email"), mime, chemin, retention),
            )
            journaliser(cur, rec_id, user, "demarrage")
    except UniqueViolation as exc:
        raise RecordingConflict() from exc
    return {"id": rec_id, "retention_until": retention.isoformat()}


def ajouter_fragment(key: str | None, rec_id: str, sequence: int, taille: int) -> bool:
    """Valide le fragment `sequence` (ordre strict, rejeu refusé) et met à jour la taille."""
    with _tx(key) as cur:
        cur.execute(
            """UPDATE room_live_enregistrement SET sequence_suivante = sequence_suivante + 1,
                      taille_octets = taille_octets + %s
               WHERE id = %s AND statut = 'en_cours' AND sequence_suivante = %s""",
            (taille, rec_id, sequence),
        )
        return cur.rowcount == 1


def terminer_enregistrement(key: str | None, rec_id: str, user: dict | None, statut: str = "termine") -> bool:
    with _tx(key) as cur:
        cur.execute(
            "UPDATE room_live_enregistrement SET statut = %s, termine_le = NOW() "
            "WHERE id = %s AND statut = 'en_cours'", (statut, rec_id))
        ok = cur.rowcount == 1
        if ok:
            journaliser(cur, rec_id, user, "arret" if statut == "termine" else statut)
        return ok


_COLONNES_ENR = ("id, salle_id, salle_nom, proprietaire_id, demarre_par_id, demarre_par_email, demarre_le, "
                 "termine_le, statut, mime, taille_octets, chemin, sequence_suivante, retention_jusqu_au")


def _enr(ligne) -> dict:
    (rid, sid, snom, oid, did, demail, debut, fin, statut, mime, taille, chemin, seq, retention) = ligne
    return {"id": rid, "room_id": sid, "room_name": snom, "owner_id": oid, "started_by_id": did,
            "started_by": demail, "started_at": debut, "ended_at": fin, "status": statut, "mime": mime,
            "size": taille, "path": chemin, "next_sequence": seq, "retention_until": retention}


def lire_enregistrement(key: str | None, rec_id: str) -> dict | None:
    with _tx(key) as cur:
        cur.execute(f"SELECT {_COLONNES_ENR} FROM room_live_enregistrement WHERE id = %s", (rec_id,))
        ligne = cur.fetchone()
    return _enr(ligne) if ligne else None


def lister_enregistrements(key: str | None, room_id: str | None = None) -> list[dict]:
    with _tx(key) as cur:
        if room_id:
            cur.execute(f"SELECT {_COLONNES_ENR} FROM room_live_enregistrement WHERE salle_id = %s "
                        "ORDER BY demarre_le DESC", (room_id,))
        else:
            cur.execute(f"SELECT {_COLONNES_ENR} FROM room_live_enregistrement ORDER BY demarre_le DESC LIMIT 200")
        return [_enr(l) for l in cur.fetchall()]


def supprimer_enregistrement(key: str | None, rec_id: str, user: dict | None, action: str = "suppression") -> None:
    with _tx(key) as cur:
        cur.execute("DELETE FROM room_live_enregistrement WHERE id = %s", (rec_id,))
        journaliser(cur, rec_id, user, action)


def purger_expires(key: str | None) -> list[str]:
    """Supprime les lignes d'enregistrements dont la rétention est dépassée ; renvoie les chemins
    de fichiers à effacer (l'appelant les supprime du disque)."""
    with _tx(key) as cur:
        cur.execute("SELECT id, chemin FROM room_live_enregistrement "
                    "WHERE retention_jusqu_au < NOW() AND statut <> 'en_cours'")
        lignes = cur.fetchall()
        for rid, _ in lignes:
            cur.execute("DELETE FROM room_live_enregistrement WHERE id = %s", (rid,))
            journaliser(cur, rid, None, "purge_retention")
    return [chemin for _, chemin in lignes if chemin]


def enregistrer_consentement(key: str | None, rec_id: str, user: dict, decision: str) -> None:
    with _tx(key) as cur:
        cur.execute(
            """INSERT INTO room_live_consentement (enregistrement_id, user_id, email, decision)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (enregistrement_id, user_id) DO UPDATE SET decision = EXCLUDED.decision,
                   decide_le = NOW()""",
            (rec_id, str(user.get("id") or user.get("sub")), user.get("email"), decision),
        )


def lire_consentements(key: str | None, rec_id: str) -> dict[str, str]:
    with _tx(key) as cur:
        cur.execute("SELECT user_id, decision FROM room_live_consentement WHERE enregistrement_id = %s", (rec_id,))
        return {uid: dec for uid, dec in cur.fetchall()}


def journaliser(cur, rec_id: str, user: dict | None, action: str) -> None:
    uid = str((user or {}).get("id") or (user or {}).get("sub") or "") or None
    cur.execute("INSERT INTO room_live_enregistrement_journal (enregistrement_id, user_id, email, action) "
                "VALUES (%s, %s, %s, %s)", (rec_id, uid, (user or {}).get("email"), action))


def journaliser_acces(key: str | None, rec_id: str, user: dict, action: str) -> None:
    with _tx(key) as cur:
        journaliser(cur, rec_id, user, action)
