"""API des enregistrements Room Live : démarrage, consentement, envoi par fragments, arrêt,
consultation, téléchargement, suppression et rétention.

Droits :
  - démarrer / arrêter : hôte ou co-hôte de la salle (l'arrêt est aussi possible par l'hôte) ;
  - consentir : tout membre de la salle ;
  - consulter / télécharger / supprimer : propriétaire de la salle, personne qui a lancé
    l'enregistrement, ou administrateur de l'entreprise (rôle vérifié en base).
Isolation : les métadonnées sont lues dans la base du jeton (entreprise ou centrale) et les
fichiers sont rangés par base ; un enregistrement d'une autre entreprise est introuvable.
"""
import asyncio
import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.schemas.room_recording import RecordingConsent, RecordingStart
from app.security.auth_dependency import exiger_role_admin, utilisateur_connecte
from app.services import recording_storage as stockage
from app.services import room_recording, room_store
from app.services.room_manager import room_manager

log = logging.getLogger("erp.room_recordings")
router = APIRouter(prefix="/api/room-live", tags=["room-live-recordings"])


def _uid(user):
    return room_manager.user_id(user)


def _erreur(exc: room_recording.EnregistrementErreur):
    return HTTPException(status_code=exc.statut, detail=exc.detail)


def _salle(user, room_id, member=True):
    room = room_manager.get_accessible(user, room_id, require_member=member)
    if not room:
        raise HTTPException(status_code=404, detail="Salle introuvable ou accès refusé.")
    return room


def _salle_de_enregistrement(user, rec_id):
    """Salle ouverte dont l'enregistrement actif porte cet identifiant (même entreprise)."""
    if not stockage.valid_recording_id(rec_id):
        raise HTTPException(status_code=404, detail="Enregistrement introuvable.")
    room_manager.hydrate(user)
    for room in list(room_manager.rooms.values()):
        rec = room.get("recording")
        if rec and rec["id"] == rec_id and room["tenant"] == room_manager.tenant(user):
            if room_manager.get_accessible(user, room["id"], require_member=True):
                return room
    raise HTTPException(status_code=404, detail="Aucun enregistrement actif avec cet identifiant.")


def _est_admin_entreprise(user: dict) -> bool:
    try:
        exiger_role_admin(utilisateur=user)
        return True
    except HTTPException:
        return False
    except Exception:
        return False


def _peut_acceder(user: dict, rec: dict, admin: bool) -> bool:
    uid = _uid(user)
    if rec["owner_id"] == uid or rec["started_by_id"] == uid:
        return True
    room = room_manager.rooms.get(rec["room_id"])
    if room and room["tenant"] == room_manager.tenant(user) and room_manager.can_manage(user, room):
        return True
    return admin


def _vue(rec: dict) -> dict:
    return {
        "id": rec["id"], "room_id": rec["room_id"], "room_name": rec["room_name"],
        "started_by": rec["started_by"], "started_at": rec["started_at"].isoformat(),
        "ended_at": rec["ended_at"].isoformat() if rec["ended_at"] else None,
        "status": rec["status"], "size": rec["size"], "mime": rec["mime"],
        "retention_until": rec["retention_until"].isoformat(),
    }


def _purger(key):
    """Purge opportuniste des enregistrements dont la rétention est dépassée."""
    try:
        for chemin in room_store.purger_expires(key):
            stockage.delete_file(chemin)
    except Exception:
        log.exception("Purge des enregistrements expirés impossible")


@router.post("/rooms/{room_id}/recordings/start")
async def start_recording(room_id: str, payload: RecordingStart, user: dict = Depends(utilisateur_connecte)):
    room = _salle(user, room_id)
    if not room_manager.can_manage(user, room):
        raise HTTPException(status_code=403, detail="Seuls l'hôte et le co-hôte peuvent enregistrer.")
    try:
        rec = await room_recording.demarrer(
            room, user, payload.mime, payload.retention_days or stockage.DEFAULT_RETENTION_DAYS)
    except room_recording.EnregistrementErreur as exc:
        raise _erreur(exc)
    await asyncio.to_thread(_purger, room_store.db_key(user))
    return {"recording": rec}


@router.post("/recordings/{rec_id}/consent")
async def consent_recording(rec_id: str, payload: RecordingConsent, user: dict = Depends(utilisateur_connecte)):
    room = _salle_de_enregistrement(user, rec_id)
    rec = room["recording"]
    uid = _uid(user)
    if uid == rec["started_by_id"]:
        raise HTTPException(status_code=400, detail="La personne qui enregistre a déjà consenti.")
    try:
        await asyncio.to_thread(room_store.enregistrer_consentement, room["db"], rec_id, user, payload.decision)
    except Exception:
        log.exception("Consentement non enregistré")
        raise HTTPException(status_code=503, detail="Consentement non enregistré, réessayez.")
    rec["consents"][uid] = payload.decision
    await room_manager.broadcast(room["id"], {
        "type": "recording_consent", "recording_id": rec_id, "user_id": uid, "decision": payload.decision})
    return {"decision": payload.decision}


@router.post("/recordings/{rec_id}/chunk")
async def upload_chunk(rec_id: str, request: Request, seq: int = Query(ge=0),
                       user: dict = Depends(utilisateur_connecte)):
    room = _salle_de_enregistrement(user, rec_id)
    rec = room["recording"]
    if rec["started_by_id"] != _uid(user):
        raise HTTPException(status_code=403, detail="Seule la personne qui enregistre peut envoyer des fragments.")
    declared = int(request.headers.get("content-length") or 0)
    if declared > stockage.MAX_CHUNK_BYTES:
        raise HTTPException(status_code=413, detail="Fragment trop volumineux.")
    data = await request.body()
    async with rec["lock"]:
        if room.get("recording") is not rec:
            raise HTTPException(status_code=409, detail="Enregistrement terminé.")
        if seq != rec["next_seq"]:
            raise HTTPException(status_code=409, detail=f"Fragment hors séquence (attendu {rec['next_seq']}).")
        try:
            taille = await asyncio.to_thread(stockage.append_chunk, rec["path"], data, rec["size"])
        except stockage.StorageError as exc:
            asyncio.create_task(room_recording.arreter(room, None, "interrompu"))
            raise HTTPException(status_code=413, detail=str(exc))
        except OSError:
            log.exception("Écriture du fragment impossible")
            asyncio.create_task(room_recording.arreter(room, None, "interrompu"))
            raise HTTPException(status_code=507, detail="Stockage indisponible, enregistrement interrompu.")
        try:
            ok = await asyncio.to_thread(room_store.ajouter_fragment, room["db"], rec_id, seq, len(data))
        except Exception:
            log.exception("Fragment non comptabilisé")
            raise HTTPException(status_code=503, detail="Base de données injoignable.")
        if not ok:
            raise HTTPException(status_code=409, detail="Fragment refusé (enregistrement clos ou rejoué).")
        rec["size"], rec["next_seq"] = taille, seq + 1
    return {"next_seq": seq + 1, "size": taille}


@router.post("/recordings/{rec_id}/stop")
async def stop_recording(rec_id: str, user: dict = Depends(utilisateur_connecte)):
    room = _salle_de_enregistrement(user, rec_id)
    rec = room["recording"]
    uid = _uid(user)
    if uid != rec["started_by_id"] and room["owner_id"] != uid:
        raise HTTPException(status_code=403, detail="Seul l'hôte ou la personne qui enregistre peut arrêter.")
    await room_recording.arreter(room, user, "termine")
    return {"message": "Enregistrement arrêté.", "recording_id": rec_id}


@router.get("/recordings")
def list_recordings(room_id: str | None = None, user: dict = Depends(utilisateur_connecte)):
    key = room_store.db_key(user)
    room_manager.hydrate(user)
    if room_id and not stockage.valid_room_id(room_id):
        raise HTTPException(status_code=404, detail="Salle introuvable.")
    _purger(key)
    admin = _est_admin_entreprise(user)
    try:
        items = room_store.lister_enregistrements(key, room_id)
    except Exception:
        log.exception("Liste des enregistrements indisponible")
        raise HTTPException(status_code=503, detail="Enregistrements indisponibles.")
    return {"recordings": [_vue(r) for r in items if _peut_acceder(user, r, admin)]}


def _charger(user, rec_id):
    if not stockage.valid_recording_id(rec_id):
        raise HTTPException(status_code=404, detail="Enregistrement introuvable.")
    key = room_store.db_key(user)
    try:
        rec = room_store.lire_enregistrement(key, rec_id)
    except Exception:
        raise HTTPException(status_code=503, detail="Enregistrements indisponibles.")
    # Même message que « inexistant » : on ne révèle pas l'existence d'un enregistrement protégé.
    if not rec or not _peut_acceder(user, rec, _est_admin_entreprise(user)):
        raise HTTPException(status_code=404, detail="Enregistrement introuvable.")
    return key, rec


@router.get("/recordings/{rec_id}/download")
def download_recording(rec_id: str, user: dict = Depends(utilisateur_connecte)):
    key, rec = _charger(user, rec_id)
    if rec["status"] == "en_cours":
        raise HTTPException(status_code=409, detail="Enregistrement en cours : arrêtez-le avant de le télécharger.")
    try:
        chemin = stockage.absolute_path(rec["path"])
    except stockage.StorageError:
        raise HTTPException(status_code=404, detail="Fichier introuvable.")
    if not chemin.is_file():
        raise HTTPException(status_code=404, detail="Fichier introuvable (déjà purgé ?).")
    room_store.journaliser_acces(key, rec_id, user, "telechargement")
    nom = quote(f"{rec['room_name'] or 'room-live'}-{rec['started_at']:%Y%m%d-%H%M}.webm", safe="")
    return FileResponse(chemin, media_type=rec["mime"],
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{nom}",
                                 "Cache-Control": "no-store"})


@router.delete("/recordings/{rec_id}")
def delete_recording(rec_id: str, user: dict = Depends(utilisateur_connecte)):
    key, rec = _charger(user, rec_id)
    if rec["status"] == "en_cours":
        raise HTTPException(status_code=409, detail="Arrêtez l'enregistrement avant de le supprimer.")
    stockage.delete_file(rec["path"])
    room_store.supprimer_enregistrement(key, rec_id, user)
    return {"message": "Enregistrement supprimé."}
