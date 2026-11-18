"""Administration des sauvegardes chiffrées. Réservé à l'administrateur du tenant."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
import io, zipfile
from pathlib import Path
import os
from pydantic import BaseModel, Field
from app.security.auth_dependency import exiger_role_admin
from app.services import sauvegardes

router=APIRouter(prefix="/api/securite/sauvegardes",tags=["sécurité - sauvegardes"])

class RestoreRequest(BaseModel):
    fichier:str=Field(min_length=1,max_length=180)
    confirmation:str=Field(min_length=8,max_length=220)

@router.post("")
def creer(utilisateur:dict=Depends(exiger_role_admin)):
    try: return sauvegardes.creer_sauvegarde(utilisateur["nomBase"])
    except Exception as e: raise HTTPException(500,str(e))

@router.post("/verifier")
def verifier(payload:RestoreRequest, utilisateur:dict=Depends(exiger_role_admin)):
    try: return sauvegardes.verifier_sauvegarde(payload.fichier)
    except FileNotFoundError as e: raise HTTPException(404,str(e))
    except Exception as e: raise HTTPException(422,str(e))

@router.post("/restaurer")
def restaurer(payload:RestoreRequest, utilisateur:dict=Depends(exiger_role_admin)):
    try:
        return sauvegardes.restaurer_sauvegarde(payload.fichier,utilisateur["nomBase"],payload.confirmation)
    except FileNotFoundError as e: raise HTTPException(404,str(e))
    except ValueError as e: raise HTTPException(422,str(e))
    except Exception as e: raise HTTPException(500,str(e))


@router.get("/{filename}")
def telecharger(filename:str, utilisateur:dict=Depends(exiger_role_admin)):
    repertoire=Path(os.getenv("ERP_BACKUP_DIR","/app/backups"))
    if Path(filename).name!=filename or not filename.endswith(".bak.enc"):
        raise HTTPException(400,"Nom de fichier invalide.")
    fichier=repertoire/filename
    if not fichier.is_file():
        raise HTTPException(404,"Sauvegarde introuvable.")
    signature=fichier.with_suffix(fichier.suffix+".hmac")
    if not signature.is_file():
        raise HTTPException(404,"Signature HMAC absente.")
    paquet=io.BytesIO()
    with zipfile.ZipFile(paquet,"w",compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(fichier,arcname=filename)
        archive.write(signature,arcname=signature.name)
    paquet.seek(0)
    return StreamingResponse(paquet,media_type="application/zip",
        headers={"Content-Disposition":f'attachment; filename="{filename}.zip"',"Cache-Control":"no-store"})
