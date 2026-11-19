
"""Administration des sauvegardes chiffrées. Réservé à l'administrateur du tenant."""

import io
import zipfile

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.security.auth_dependency import exiger_role_admin
from app.services import sauvegardes

router = APIRouter(
    prefix="/api/securite/sauvegardes",
    tags=["sécurité - sauvegardes"],
)


class RestoreRequest(BaseModel):
    fichier: str = Field(min_length=1, max_length=180)
    confirmation: str = Field(min_length=8, max_length=220)


@router.post("")
def creer(utilisateur: dict = Depends(exiger_role_admin)):
    try:
        return sauvegardes.creer_sauvegarde(utilisateur["nomBase"])
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Impossible de créer la sauvegarde.",
        )


@router.post("/verifier")
def verifier(
    payload: RestoreRequest,
    utilisateur: dict = Depends(exiger_role_admin),
):
    try:
        return sauvegardes.verifier_sauvegarde(
            payload.fichier,
            utilisateur["nomBase"],
        )
    except FileNotFoundError:
        raise HTTPException(404, "Sauvegarde introuvable.")
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception:
        raise HTTPException(500, "Erreur lors de la vérification.")


@router.post("/restaurer")
def restaurer(
    payload: RestoreRequest,
    utilisateur: dict = Depends(exiger_role_admin),
):
    try:
        return sauvegardes.restaurer_sauvegarde(
            payload.fichier,
            utilisateur["nomBase"],
            payload.confirmation,
        )
    except FileNotFoundError:
        raise HTTPException(404, "Sauvegarde introuvable.")
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception:
        raise HTTPException(500, "Erreur lors de la restauration.")


@router.get("/{filename}")
def telecharger(
    filename: str,
    utilisateur: dict = Depends(exiger_role_admin),
):
    try:
        fichier, signature = sauvegardes.obtenir_fichiers_sauvegarde(
            filename,
            utilisateur["nomBase"],
        )
    except FileNotFoundError:
        raise HTTPException(404, "Sauvegarde introuvable.")
    except ValueError:
        raise HTTPException(403, "Accès à cette sauvegarde interdit.")

    paquet = io.BytesIO()

    with zipfile.ZipFile(
        paquet, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        archive.write(fichier, arcname=filename)
        archive.write(signature, arcname=signature.name)

    paquet.seek(0)

    return StreamingResponse(
        paquet,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}.zip"',
            "Cache-Control": "no-store",
        },
    )
