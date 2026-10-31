"""Gestion temporaire des salles Room Live (aucune migration SQL)."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any


class RoomManager:
    def __init__(self):
        self.rooms: dict[str, dict[str, Any]] = {}
        self.connections: dict[str, dict[str, Any]] = {}
        self.files: dict[str, dict[str, Any]] = {}
        self.lock = asyncio.Lock()

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
            "is_private": is_private, "tenant": self.tenant(user),
            "owner_id": uid, "owner_email": user.get("email"),
            "created_at": now, "invited_emails": set(),
            "participants": {uid: {
                "user_id": uid, "email": user.get("email"), "role": "host",
                "joined_at": now, "blocked": False,
            }},
            "messages": [],
        }
        async with self.lock:
            self.rooms[room_id] = room
        return self.public_room(room)

    def public_room(self, room):
        return {
            "id": room["id"], "name": room["name"], "description": room["description"],
            "is_private": room["is_private"], "owner_email": room["owner_email"],
            "created_at": room["created_at"],
            "participants": [self.public_participant(p) for p in room["participants"].values()],
            "participant_count": len(room["participants"]),
        }

    def get_accessible(self, user: dict, room_id: str, require_member: bool = False):
        room = self.rooms.get(room_id)
        if not room or room["tenant"] != self.tenant(user):
            return None
        uid, email = self.user_id(user), (user.get("email") or "").lower()
        participant = room["participants"].get(uid)
        invited = email in room["invited_emails"]
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
            return self.public_room(room)

    async def leave(self, room_id: str, uid: str):
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
                if not room["participants"]:
                    self.rooms.pop(room_id, None)
                    self.connections.pop(room_id, None)
                    for file_id in [fid for fid, item in self.files.items() if item["room_id"] == room_id]:
                        self.files.pop(file_id, None)

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
