"""Cycle de vie d'un enregistrement Room Live (état en mémoire + métadonnées en base).

Principe technique : le navigateur de l'hôte (ou co-hôte) compose l'enregistrement
(mosaïque vidéo + mélange audio) avec MediaRecorder et l'envoie par fragments ordonnés.
Le serveur valide les droits, l'ordre, la taille et le consentement, puis stocke le fichier.
Les flux des participants qui n'ont pas accepté ne sont pas mixés par l'application ; ce contrôle
s'exerce côté client (une architecture SFU permettrait de l'imposer côté serveur).
"""
from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timezone

from app.services import recording_storage as stockage
from app.services import room_store
from app.services.room_manager import room_manager

_RE_MIME = re.compile(r"^(video|audio)/webm$")


class EnregistrementErreur(Exception):
    def __init__(self, statut: int, detail: str):
        super().__init__(detail)
        self.statut = statut
        self.detail = detail


def actif(room: dict) -> dict | None:
    return room.get("recording")


def normaliser_mime(mime: str) -> str:
    base = (mime or "video/webm").split(";")[0].strip().lower()
    if not _RE_MIME.match(base):
        raise EnregistrementErreur(400, "Format d'enregistrement non pris en charge (WebM uniquement).")
    return base


def public(rec: dict) -> dict:
    return {
        "id": rec["id"], "started_by": rec["started_by"], "started_by_id": rec["started_by_id"],
        "started_at": rec["started_at"],
        "retention_until": rec["retention_until"],
        "consents": dict(rec["consents"]),
    }


async def demarrer(room: dict, user: dict, mime: str, retention_jours: int) -> dict:
    if actif(room):
        raise EnregistrementErreur(409, "Un enregistrement est déjà en cours dans cette salle.")
    mime = normaliser_mime(mime)
    retention_jours = max(1, min(int(retention_jours), stockage.MAX_RETENTION_DAYS))
    rec_id = os.urandom(16).hex()
    uid = room_manager.user_id(user)
    try:
        chemin = stockage.relative_path(room["db"], room["id"], rec_id, mime)
        meta = await asyncio.to_thread(room_store.creer_enregistrement, room, user, rec_id, mime, chemin,
                                       retention_jours)
    except room_store.RecordingConflict:
        raise EnregistrementErreur(409, "Un enregistrement est déjà en cours dans cette salle.")
    except stockage.StorageError as exc:
        raise EnregistrementErreur(400, str(exc))
    except Exception:
        raise EnregistrementErreur(503, "Enregistrement indisponible : base de données injoignable.")
    now = datetime.now(timezone.utc).isoformat()
    rec = {
        "id": rec_id, "started_by_id": uid, "started_by": user.get("email"), "started_at": now,
        "retention_until": meta["retention_until"], "mime": mime, "path": chemin,
        "consents": {uid: "accepte"}, "size": 0, "next_seq": 0, "lock": asyncio.Lock(),
    }
    room["recording"] = rec
    # Le démarreur consent par construction ; la trace est conservée pour l'audit.
    try:
        await asyncio.to_thread(room_store.enregistrer_consentement, room["db"], rec_id, user, "accepte")
    except Exception:
        pass
    await room_manager.broadcast(room["id"], {"type": "recording_started", "recording": public(rec)})
    return public(rec)


async def arreter(room: dict, user: dict | None, statut: str = "termine") -> bool:
    rec = actif(room)
    if not rec:
        return False
    async with rec["lock"]:
        room["recording"] = None
        try:
            await asyncio.to_thread(room_store.terminer_enregistrement, room["db"], rec["id"], user, statut)
        except Exception:
            pass
    await room_manager.broadcast(room["id"], {"type": "recording_stopped", "recording_id": rec["id"],
                                              "status": statut})
    return True


async def interrompre_si_enregistreur(room: dict, uid: str) -> None:
    """Si la personne qui enregistre quitte / est retirée / se déconnecte, l'enregistrement est
    clos en « interrompu » (le fichier partiel reste consultable)."""
    rec = actif(room)
    if rec and rec["started_by_id"] == uid:
        await arreter(room, None, "interrompu")
