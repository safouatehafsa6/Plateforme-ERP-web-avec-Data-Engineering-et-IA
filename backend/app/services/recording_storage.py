"""Stockage disque des enregistrements Room Live.

Arborescence : <RECORDINGS_DIR>/<base entreprise | central>/<salle>/<enregistrement>.webm
Tous les identifiants sont validés (hexadécimal strict) avant de construire un chemin :
aucune valeur fournie par le client n'est jamais concaténée telle quelle.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

RECORDINGS_DIR = Path(os.getenv("RECORDINGS_DIR", "/app/data/room_recordings"))
MAX_RECORDING_BYTES = int(os.getenv("RECORDING_MAX_MB", "500")) * 1024 * 1024
MAX_CHUNK_BYTES = int(os.getenv("RECORDING_MAX_CHUNK_MB", "16")) * 1024 * 1024
DEFAULT_RETENTION_DAYS = int(os.getenv("RECORDING_RETENTION_DAYS", "30"))
MAX_RETENTION_DAYS = 365

_RE_ROOM = re.compile(r"^[0-9a-f]{12}$")
_RE_REC = re.compile(r"^[0-9a-f]{32}$")
_RE_BASE = re.compile(r"^[A-Za-z0-9_]{1,63}$")
ALLOWED_MIME = {"video/webm": "webm", "audio/webm": "webm"}


class StorageError(Exception):
    pass


def valid_room_id(value: str) -> bool:
    return bool(value and _RE_ROOM.match(value))


def valid_recording_id(value: str) -> bool:
    return bool(value and _RE_REC.match(value))


def _tenant_dir(db_key: str | None) -> str:
    if db_key is None:
        return "central"
    if not _RE_BASE.match(db_key):
        raise StorageError("Nom de base invalide.")
    return "base_" + db_key


def relative_path(db_key: str | None, room_id: str, rec_id: str, mime: str) -> str:
    if not valid_room_id(room_id) or not valid_recording_id(rec_id):
        raise StorageError("Identifiant invalide.")
    ext = ALLOWED_MIME.get(mime)
    if not ext:
        raise StorageError("Format d'enregistrement non autorisé.")
    return f"{_tenant_dir(db_key)}/{room_id}/{rec_id}.{ext}"


def absolute_path(relative: str) -> Path:
    """Résout un chemin relatif stocké en base et refuse tout ce qui sortirait du dossier racine."""
    root = RECORDINGS_DIR.resolve()
    path = (root / relative).resolve()
    if root != path and root not in path.parents:
        raise StorageError("Chemin hors du dossier d'enregistrements.")
    return path


def append_chunk(relative: str, data: bytes, current_size: int) -> int:
    """Ajoute un fragment à la fin du fichier ; renvoie la nouvelle taille."""
    if not data:
        raise StorageError("Fragment vide.")
    if len(data) > MAX_CHUNK_BYTES:
        raise StorageError("Fragment trop volumineux.")
    if current_size + len(data) > MAX_RECORDING_BYTES:
        raise StorageError("Taille maximale d'enregistrement atteinte.")
    path = absolute_path(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "ab") as handle:
        handle.write(data)
    return current_size + len(data)


def delete_file(relative: str | None) -> bool:
    if not relative:
        return False
    try:
        path = absolute_path(relative)
        path.unlink(missing_ok=True)
        return True
    except (OSError, StorageError):
        return False
