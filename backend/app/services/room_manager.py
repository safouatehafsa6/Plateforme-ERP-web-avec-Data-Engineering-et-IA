"""Gestion des salles Room Live.

L'état « temps réel » (connexions WebSocket, flux) reste en mémoire ; salles, participants,
invitations et messages sont en plus persistés (room_store) et rechargés à la demande après un
redémarrage. ROOM_LIVE_PERSIST=0 désactive la persistance (tests unitaires sans base)."""
from __future__ import annotations

import asyncio
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services import room_store


INVITATION_HEURES = 48  # durée de validité d'une invitation


def persistance_active() -> bool:
    return os.getenv("ROOM_LIVE_PERSIST", "1") != "0"


class RoomManager:
    def __init__(self):
        self.rooms: dict[str, dict[str, Any]] = {}
        self.connections: dict[str, dict[str, Any]] = {}
        self.files: dict[str, dict[str, Any]] = {}
        self.lock = asyncio.Lock()
        self._charges: set = set()  # bases dont les salles ont déjà été rechargées
        self._verrou_chargement = threading.Lock()

    def hydrate(self, user: dict) -> None:
        """Recharge une seule fois par base les salles persistées (après redémarrage)."""
        if not persistance_active():
            return
        cle = room_store.db_key(user)
        if cle in self._charges:
            return
        with self._verrou_chargement:
            if cle in self._charges:
                return
            salles = room_store.charger_salles(cle, self.tenant(user))
            if salles is None:
                return  # erreur : on réessaiera au prochain accès
            for rid, salle in salles.items():
                self.rooms.setdefault(rid, salle)
            self._charges.add(cle)

    async def persist(self, fonction, *args) -> None:
        """Exécute une écriture de persistance hors de la boucle asynchrone."""
        if persistance_active():
            await asyncio.to_thread(fonction, *args)

    @staticmethod
    def tenant(user: dict) -> str:
        return str(user.get("entrepriseId") or user.get("nomBase") or user.get("sub") or "platform")

    @staticmethod
    def user_id(user: dict) -> str:
        return str(user.get("id") or user.get("sub") or user.get("email") or "")

    @staticmethod
    def public_participant(participant: dict) -> dict:
        return {k: participant.get(k) for k in ("user_id", "email", "role", "joined_at", "blocked")}

    async def create(self, user: dict, name: str, description: str, is_private: bool):
        room_id = uuid.uuid4().hex[:12]
        uid = self.user_id(user)
        now = datetime.now(timezone.utc).isoformat()
        room = {
            "id": room_id, "name": name, "description": description,
            "is_private": is_private, "tenant": self.tenant(user), "db": room_store.db_key(user),
            "owner_id": uid, "owner_email": user.get("email"),
            "created_at": now, "invited_emails": set(), "invite_expiry": {},
            "last_summary": None,
            "participants": {uid: {
                "user_id": uid, "email": user.get("email"), "role": "host",
                "joined_at": now, "blocked": False,
            }},
            "messages": [],
        }
        async with self.lock:
            self.rooms[room_id] = room
        await self.persist(room_store.enregistrer_salle, room)
        return self.public_room(room)

    @staticmethod
    def can_manage(user: dict, room: dict) -> bool:
        participant = room["participants"].get(RoomManager.user_id(user), {})
        return room["owner_id"] == RoomManager.user_id(user) or participant.get("role") == "cohost"

    def public_room(self, room):
        return {
            "id": room["id"], "name": room["name"], "description": room["description"],
            "is_private": room["is_private"], "owner_email": room["owner_email"],
            "created_at": room["created_at"],
            "participants": [self.public_participant(p) for p in room["participants"].values()],
            "participant_count": len(room["participants"]),
        }

    def invite(self, room: dict, email: str, heures: int = INVITATION_HEURES) -> datetime:
        """Enregistre une invitation avec date d'expiration."""
        email = email.strip().lower()
        expire = datetime.now(timezone.utc) + timedelta(hours=heures)
        room["invited_emails"].add(email)
        room.setdefault("invite_expiry", {})[email] = expire
        return expire

    @staticmethod
    def is_invited(room: dict, email: str) -> bool:
        """Vrai si l'e-mail a une invitation non expirée (l'expirée est purgée)."""
        email = (email or "").lower()
        if email not in room["invited_emails"]:
            return False
        expire = room.get("invite_expiry", {}).get(email)
        if expire and expire < datetime.now(timezone.utc):
            room["invited_emails"].discard(email)
            room["invite_expiry"].pop(email, None)
            return False
        return True

    def get_accessible(self, user: dict, room_id: str, require_member: bool = False):
        self.hydrate(user)
        room = self.rooms.get(room_id)
        if not room or room["tenant"] != self.tenant(user):
            return None
        uid, email = self.user_id(user), (user.get("email") or "").lower()
        participant = room["participants"].get(uid)
        invited = self.is_invited(room, email)
        if room["is_private"] and not participant and not invited:
            return None
        if require_member and not participant:
            return None
        if participant and participant.get("blocked"):
            return None
        return room

    async def join(self, user: dict, room_id: str):
        async with self.lock:
            room = self.get_accessible(user, room_id)
            if not room:
                return None
            uid = self.user_id(user)
            if uid not in room["participants"]:
                room["participants"][uid] = {
                    "user_id": uid, "email": user.get("email"), "role": "member",
                    "joined_at": datetime.now(timezone.utc).isoformat(), "blocked": False,
                }
            room["invited_emails"].discard((user.get("email") or "").lower())
            room.get("invite_expiry", {}).pop((user.get("email") or "").lower(), None)
            participant = room["participants"][uid]
            public = self.public_room(room)
        await self.persist(room_store.enregistrer_participant, room, participant)
        await self.persist(room_store.supprimer_invitation, room, (user.get("email") or "").lower())
        return public

    async def update_participant_role(self, room_id: str, participant_id: str, role: str):
        async with self.lock:
            room = self.rooms.get(room_id)
            if not room or participant_id not in room["participants"]:
                return None
            if participant_id == room["owner_id"]:
                return None
            room["participants"][participant_id]["role"] = role
            participant = room["participants"][participant_id]
            public = self.public_room(room)
        await self.persist(room_store.enregistrer_participant, room, participant)
        return public

    async def leave(self, room_id: str, uid: str):
        ferme = None
        nouveau_hote = False
        async with self.lock:
            room = self.rooms.get(room_id)
            if room:
                room["participants"].pop(uid, None)
                self.connections.get(room_id, {}).pop(uid, None)
                if room["owner_id"] == uid and room["participants"]:
                    next_host = next(iter(room["participants"].values()))
                    next_host["role"] = "host"
                    room["owner_id"] = next_host["user_id"]
                    room["owner_email"] = next_host["email"]
                    nouveau_hote = True
                if not room["participants"]:
                    self.rooms.pop(room_id, None)
                    self.connections.pop(room_id, None)
                    for file_id in [fid for fid, item in self.files.items() if item["room_id"] == room_id]:
                        self.files.pop(file_id, None)
                    ferme = room
        if room is None:
            return
        if ferme is not None:
            await self.persist(room_store.fermer_salle, ferme["db"], room_id)
        else:
            await self.persist(room_store.retirer_participant, room, uid)
            if nouveau_hote:
                await self.persist(room_store.enregistrer_proprietaire, room)

    async def broadcast(self, room_id: str, payload: dict, exclude: str | None = None):
        peers = list(self.connections.get(room_id, {}).items())
        for uid, websocket in peers:
            if uid == exclude:
                continue
            try:
                await websocket.send_json(payload)
            except Exception:
                self.connections.get(room_id, {}).pop(uid, None)


room_manager = RoomManager()
