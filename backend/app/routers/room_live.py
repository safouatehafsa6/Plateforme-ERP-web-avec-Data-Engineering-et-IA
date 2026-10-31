"""API Room Live : salles temporaires, invitations, fichiers et WebSocket."""
import os
import jwt
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse
from io import BytesIO
from urllib.parse import quote

from app.security.auth_dependency import utilisateur_connecte
from app.security.sessions import verifier_session
from app.schemas.room_live import RoomCreate, RoomInvite
from app.services.room_manager import room_manager

router = APIRouter(prefix="/api/room-live", tags=["room-live"])


def _uid(user):
    return room_manager.user_id(user)


def _require_room(user, room_id, member=False):
    room = room_manager.get_accessible(user, room_id, require_member=member)
    if not room:
        raise HTTPException(status_code=404, detail="Salle introuvable ou accès refusé.")
    return room


def _require_host(user, room):
    if room["owner_id"] != _uid(user):
        raise HTTPException(status_code=403, detail="Seul le créateur de la salle peut effectuer cette action.")


@router.get("/rooms")
def list_rooms(user: dict = Depends(utilisateur_connecte)):
    result = []
    for room in list(room_manager.rooms.values()):
        if room["tenant"] == room_manager.tenant(user):
            if room_manager.get_accessible(user, room["id"]):
                result.append(room_manager.public_room(room))
    return {"rooms": result}


@router.post("/rooms")
async def create_room(payload: RoomCreate, user: dict = Depends(utilisateur_connecte)):
    room = await room_manager.create(user, payload.name, payload.description, payload.is_private)
    return {"room": room}


@router.get("/rooms/{room_id}")
def get_room(room_id: str, user: dict = Depends(utilisateur_connecte)):
    return {"room": room_manager.public_room(_require_room(user, room_id))}


@router.post("/rooms/{room_id}/join")
async def join_room(room_id: str, user: dict = Depends(utilisateur_connecte)):
    room = await room_manager.join(user, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Salle introuvable ou invitation nécessaire.")
    await room_manager.broadcast(room_id, {"type": "participants", "room": room})
    return {"room": room}


@router.post("/rooms/{room_id}/invite")
async def invite_room(room_id: str, payload: RoomInvite, user: dict = Depends(utilisateur_connecte)):
    room = _require_room(user, room_id, member=True)
    _require_host(user, room)
    email = payload.email.strip().lower()
    room["invited_emails"].add(email)
    return {"message": "Invitation enregistrée. Le participant pourra rejoindre avec son compte de la même entreprise."}


@router.post("/rooms/{room_id}/participants/{participant_id}/remove")
async def remove_participant(room_id: str, participant_id: str, user: dict = Depends(utilisateur_connecte)):
    room = _require_room(user, room_id, member=True)
    _require_host(user, room)
    if participant_id == room["owner_id"]:
        raise HTTPException(status_code=400, detail="Le créateur ne peut pas être retiré de sa propre salle.")
    room["participants"].pop(participant_id, None)
    socket = room_manager.connections.get(room_id, {}).pop(participant_id, None)
    if socket:
        try:
            await socket.close(code=4403)
        except Exception:
            pass
    await room_manager.broadcast(room_id, {"type": "participant_removed", "user_id": participant_id})
    await room_manager.broadcast(room_id, {"type": "participants", "room": room_manager.public_room(room)})
    return {"message": "Participant retiré."}


@router.post("/rooms/{room_id}/participants/{participant_id}/block")
async def block_participant(room_id: str, participant_id: str, user: dict = Depends(utilisateur_connecte)):
    room = _require_room(user, room_id, member=True)
    _require_host(user, room)
    participant = room["participants"].get(participant_id)
    if not participant or participant_id == room["owner_id"]:
        raise HTTPException(status_code=404, detail="Participant introuvable.")
    participant["blocked"] = True
    socket = room_manager.connections.get(room_id, {}).pop(participant_id, None)
    if socket:
        try:
            await socket.close(code=4403)
        except Exception:
            pass
    await room_manager.broadcast(room_id, {"type": "participant_blocked", "user_id": participant_id})
    return {"message": "Participant bloqué."}


@router.post("/rooms/{room_id}/leave")
async def leave_room(room_id: str, user: dict = Depends(utilisateur_connecte)):
    _require_room(user, room_id, member=True)
    await room_manager.leave(room_id, _uid(user))
    remaining = room_manager.rooms.get(room_id)
    await room_manager.broadcast(room_id, {
        "type": "participants",
        "room": room_manager.public_room(remaining) if remaining else None,
        "room_id": room_id,
    })
    return {"message": "Vous avez quitté la salle."}


@router.post("/rooms/{room_id}/files")
async def upload_file(room_id: str, file: UploadFile = File(...), user: dict = Depends(utilisateur_connecte)):
    room = _require_room(user, room_id, member=True)
    content = await file.read(15 * 1024 * 1024 + 1)
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Fichier limité à 15 Mo.")
    file_id = os.urandom(12).hex()
    room_manager.files[file_id] = {
        "room_id": room_id, "tenant": room["tenant"], "name": file.filename or "document",
        "content_type": file.content_type or "application/octet-stream", "content": content,
    }
    await room_manager.broadcast(room_id, {"type": "file_shared", "file": {
        "id": file_id, "name": file.filename or "document", "size": len(content),
        "content_type": file.content_type or "application/octet-stream",
        "sender": user.get("email"),
    }}, exclude=_uid(user))
    return {"id": file_id, "name": file.filename, "size": len(content)}


@router.get("/files/{file_id}")
def download_file(file_id: str, user: dict = Depends(utilisateur_connecte)):
    item = room_manager.files.get(file_id)
    if not item or item["tenant"] != room_manager.tenant(user):
        raise HTTPException(status_code=404, detail="Fichier introuvable.")
    room = room_manager.get_accessible(user, item["room_id"], require_member=True)
    if not room:
        raise HTTPException(status_code=403, detail="Accès refusé.")
    safe_name = quote(item["name"], safe="")
    return StreamingResponse(BytesIO(item["content"]), media_type=item["content_type"],
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}"})


def _websocket_user(token: str):
    try:
        claims = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"])
        verifier_session(claims)
        return claims
    except Exception:
        return None


@router.websocket("/ws/{room_id}")
async def room_websocket(websocket: WebSocket, room_id: str, token: str = ""):
    user = _websocket_user(token)
    if not user:
        await websocket.close(code=4401)
        return
    room = room_manager.get_accessible(user, room_id, require_member=True)
    if not room:
        await websocket.close(code=4403)
        return
    uid = _uid(user)
    await websocket.accept()
    room_manager.connections.setdefault(room_id, {})[uid] = websocket
    await room_manager.broadcast(room_id, {"type": "presence", "user_id": uid, "status": "joined"}, exclude=uid)
    await websocket.send_json({"type": "history", "messages": room["messages"][-100:]})
    await websocket.send_json({"type": "participants", "room": room_manager.public_room(room)})
    try:
        while True:
            data = await websocket.receive_json()
            # Revalider l'appartenance à chaque message pour empêcher un
            # participant retiré/bloqué de continuer à émettre.
            room = room_manager.get_accessible(user, room_id, require_member=True)
            if not room or room_manager.connections.get(room_id, {}).get(uid) is not websocket:
                await websocket.close(code=4403)
                break
            kind = data.get("type")
            if kind == "chat":
                content = str(data.get("content", "")).strip()[:4000]
                if not content:
                    continue
                message = {
                    "id": os.urandom(8).hex(), "content": content,
                    "sender_id": uid, "sender": user.get("email"),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                room["messages"].append(message)
                room["messages"] = room["messages"][-200:]
                await room_manager.broadcast(room_id, {"type": "chat", "message": message})
            elif kind in ("offer", "answer", "ice-candidate"):
                target = str(data.get("target_user_id", ""))
                if target in room_manager.connections.get(room_id, {}):
                    await room_manager.connections[room_id][target].send_json({
                        "type": kind, "from_user_id": uid, "payload": data.get("payload", {}),
                    })
            elif kind == "media_state":
                await room_manager.broadcast(room_id, {"type": "media_state", "user_id": uid,
                    "audio": bool(data.get("audio")), "video": bool(data.get("video"))}, exclude=uid)
    except WebSocketDisconnect:
        pass
    finally:
        if room_manager.connections.get(room_id, {}).get(uid) is websocket:
            room_manager.connections.get(room_id, {}).pop(uid, None)
        await room_manager.broadcast(room_id, {"type": "presence", "user_id": uid, "status": "left"})
