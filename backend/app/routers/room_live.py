"""API Room Live : salles temporaires, invitations, fichiers et WebSocket."""
import asyncio
import logging
import os
import re
import time
import jwt
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse
from io import BytesIO
from urllib.parse import quote

from app.security.auth_dependency import utilisateur_connecte
from app.security.sessions import verifier_session
from app.schemas.room_live import RoomCreate, RoomInvite, RoomUpdate, ParticipantRoleUpdate
from app.services import room_recording, room_store
from app.services.room_manager import room_manager
from app.services.room_summary import resumer
from app.utils.email_sender import envoyer_email

logger = logging.getLogger("erp.room_live")

# URL publique du frontend, utilisée pour le lien d'accès dans les e-mails
# d'invitation. Définie côté serveur (jamais lue depuis la requête) pour
# qu'un hôte ne puisse pas faire envoyer un lien vers un autre site.
FRONTEND_PUBLIC_URL = os.getenv("FRONTEND_PUBLIC_URL", "http://192.168.244.130:3000").rstrip("/")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DELAI_RESUME_SECONDES = 20  # anti-abus : limite les appels répétés au LLM

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
        raise HTTPException(status_code=403, detail="Action réservée à l'hôte de la salle.")

def _require_manager(user, room):
    if not room_manager.can_manage(user, room):
        raise HTTPException(status_code=403, detail="Action réservée à l'hôte ou au co-hôte.")


@router.get("/rooms")
def list_rooms(user: dict = Depends(utilisateur_connecte)):
    room_manager.hydrate(user)
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
    _require_manager(user, room)
    email = payload.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Adresse e-mail invalide.")
    expire = room_manager.invite(room, email)
    await room_manager.persist(room_store.enregistrer_invitation, room, email, expire)

    nom_salle = re.sub(r"[\r\n]+", " ", room["name"]).strip()
    lien = f"{FRONTEND_PUBLIC_URL}/room-live?room={room_id}"
    corps = (
        f"Bonjour,\n\n"
        f"{user.get('email')} vous invite à rejoindre la salle Room Live « {nom_salle} ».\n\n"
        f"Lien d'accès : {lien}\n\n"
        f"Connectez-vous avec votre compte de la même entreprise pour entrer dans la salle.\n"
        f"Cette invitation expire le {expire.strftime('%d/%m/%Y à %H:%M')} (UTC).\n\n"
        f"— BENJEDDOU ERP"
    )
    try:
        # smtplib est bloquant : exécuté hors de la boucle asynchrone.
        await asyncio.to_thread(envoyer_email, email, f"Invitation Room Live : {nom_salle}", corps)
        envoye = True
    except Exception:
        logger.exception("Envoi de l'invitation Room Live impossible")
        envoye = False

    return {
        "email_sent": envoye,
        "expires_at": expire.isoformat(),
        "link": lien,
        "message": (
            f"Invitation envoyée à {email} (valable 48 h)."
            if envoye else
            "Invitation enregistrée (valable 48 h), mais l'e-mail n'a pas pu être envoyé : partagez le lien manuellement."
        ),
    }


@router.patch("/rooms/{room_id}")
async def update_room(room_id: str, payload: RoomUpdate, user: dict = Depends(utilisateur_connecte)):
    room = _require_room(user, room_id, member=True)
    _require_host(user, room)
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes:
        room["name"] = changes["name"].strip()
    if "description" in changes:
        room["description"] = changes["description"].strip()
    if "is_private" in changes:
        room["is_private"] = changes["is_private"]
    await room_manager.persist(room_store.enregistrer_salle, room)
    public = room_manager.public_room(room)
    await room_manager.broadcast(room_id, {"type": "room_updated", "room": public})
    return {"room": public}


@router.delete("/rooms/{room_id}")
async def close_room(room_id: str, user: dict = Depends(utilisateur_connecte)):
    room = _require_room(user, room_id, member=True)
    _require_host(user, room)
    await room_recording.arreter(room, user, "termine")
    await room_manager.broadcast(room_id, {"type": "room_closed", "room_id": room_id})
    for socket in list(room_manager.connections.get(room_id, {}).values()):
        try:
            await socket.close(code=4000, reason="Salle fermée par l'hôte")
        except Exception:
            pass
    room_manager.rooms.pop(room_id, None)
    room_manager.connections.pop(room_id, None)
    for file_id in [fid for fid, item in room_manager.files.items() if item["room_id"] == room_id]:
        room_manager.files.pop(file_id, None)
    await room_manager.persist(room_store.fermer_salle, room["db"], room_id)
    return {"message": "Salle fermée."}


@router.delete("/rooms/{room_id}/invitations/{email}")
async def revoke_invitation(room_id: str, email: str, user: dict = Depends(utilisateur_connecte)):
    room = _require_room(user, room_id, member=True)
    _require_manager(user, room)
    normalized = email.strip().lower()
    room["invited_emails"].discard(normalized)
    room.get("invite_expiry", {}).pop(normalized, None)
    await room_manager.persist(room_store.supprimer_invitation, room, normalized)
    return {"message": "Invitation révoquée."}


@router.patch("/rooms/{room_id}/participants/{participant_id}/role")
async def update_participant_role(room_id: str, participant_id: str, payload: ParticipantRoleUpdate, user: dict = Depends(utilisateur_connecte)):
    room = _require_room(user, room_id, member=True)
    _require_host(user, room)
    participant = room["participants"].get(participant_id)
    if not participant or participant_id == room["owner_id"]:
        raise HTTPException(status_code=404, detail="Participant introuvable.")
    if participant.get("role") == "cohost" and payload.role == "cohost":
        return {"room": room_manager.public_room(room)}
    public = await room_manager.update_participant_role(room_id, participant_id, payload.role)
    await room_manager.broadcast(room_id, {"type": "participants", "room": public})
    return {"room": public}


@router.post("/rooms/{room_id}/summary")
async def summarize_room(room_id: str, user: dict = Depends(utilisateur_connecte)):
    """Résumé de la réunion à partir des messages de la salle (membres uniquement)."""
    room = _require_room(user, room_id, member=True)

    dernier = room.get("last_summary")
    if dernier and time.monotonic() - dernier["at"] < DELAI_RESUME_SECONDES \
            and dernier["message_count"] == len(room["messages"]):
        return {**dernier["result"], "cached": True}

    participants = [p.get("email") or "" for p in room["participants"].values()]
    messages = list(room["messages"])
    resultat = await asyncio.to_thread(resumer, room["name"], participants, messages)
    room["last_summary"] = {"at": time.monotonic(), "message_count": len(messages), "result": resultat}
    return {**resultat, "cached": False}


@router.post("/rooms/{room_id}/participants/{participant_id}/remove")
async def remove_participant(room_id: str, participant_id: str, user: dict = Depends(utilisateur_connecte)):
    room = _require_room(user, room_id, member=True)
    _require_manager(user, room)
    if participant_id == room["owner_id"]:
        raise HTTPException(status_code=400, detail="Le créateur ne peut pas être retiré de sa propre salle.")
    if room["participants"].get(participant_id, {}).get("role") == "cohost" and room["owner_id"] != _uid(user):
        raise HTTPException(status_code=403, detail="Un co-hôte ne peut pas retirer un autre co-hôte.")
    room["participants"].pop(participant_id, None)
    await room_manager.persist(room_store.retirer_participant, room, participant_id)
    await room_recording.interrompre_si_enregistreur(room, participant_id)
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
    _require_manager(user, room)
    participant = room["participants"].get(participant_id)
    if not participant or participant_id == room["owner_id"]:
        raise HTTPException(status_code=404, detail="Participant introuvable.")
    if participant.get("role") == "cohost" and room["owner_id"] != _uid(user):
        raise HTTPException(status_code=403, detail="Un co-hôte ne peut pas bloquer un autre co-hôte.")
    participant["blocked"] = True
    await room_manager.persist(room_store.enregistrer_participant, room, participant)
    await room_recording.interrompre_si_enregistreur(room, participant_id)
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
    room = _require_room(user, room_id, member=True)
    await room_recording.interrompre_si_enregistreur(room, _uid(user))
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
    if room["participants"].get(_uid(user), {}).get("role") == "observer":
        raise HTTPException(status_code=403, detail="Le mode observateur ne permet pas de partager des fichiers.")
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


DELAI_RECONNEXION_ENREGISTREUR = 20  # secondes de tolérance avant d'interrompre l'enregistrement


async def _interrompre_apres_delai(room_id: str, uid: str):
    """Si la personne qui enregistre ne se reconnecte pas à temps, l'enregistrement est clos."""
    await asyncio.sleep(DELAI_RECONNEXION_ENREGISTREUR)
    room = room_manager.rooms.get(room_id)
    if room and uid not in room_manager.connections.get(room_id, {}):
        await room_recording.interrompre_si_enregistreur(room, uid)


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
    if room_recording.actif(room):
        await websocket.send_json({"type": "recording_started", "recording": room_recording.public(room["recording"])})
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
                if room["participants"].get(uid, {}).get("role") == "observer":
                    await websocket.send_json({"type": "error", "message": "Le mode observateur ne permet pas d'envoyer des messages."})
                    continue
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
                await room_manager.persist(room_store.enregistrer_message, room, message)
                await room_manager.broadcast(room_id, {"type": "chat", "message": message})
            elif kind in ("offer", "answer", "ice-candidate"):
                if kind == "offer" and room["participants"].get(uid, {}).get("role") == "observer":
                    continue
                target = str(data.get("target_user_id", ""))
                if target == uid or target not in room["participants"]:
                    continue
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
        room_now = room_manager.rooms.get(room_id)
        if room_now and room_recording.actif(room_now) and room_now["recording"]["started_by_id"] == uid:
            asyncio.create_task(_interrompre_apres_delai(room_id, uid))
