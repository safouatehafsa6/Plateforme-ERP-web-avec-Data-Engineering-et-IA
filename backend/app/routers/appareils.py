"""Gestion des appareils : les siens (tous profils) et, pour l'administrateur
de l'entreprise, ceux de SON entreprise uniquement."""
from fastapi import APIRouter, Depends, HTTPException, Request

from app.security import appareils as svc
from app.security.audit import journaliser
from app.security.auth_dependency import exiger_role_admin, utilisateur_connecte

router = APIRouter(prefix="/api/appareils", tags=["appareils"])
router_admin = APIRouter(prefix="/api/admin/appareils", tags=["appareils-admin"])

_EVENEMENT = {
    "autoriser": "appareil_autorise",
    "reactiver": "appareil_reactive",
    "bloquer": "appareil_bloque",
    "deconnecter": "appareil_deconnecte",
    "supprimer": "appareil_supprime",
}
_MESSAGE = {
    "autoriser": "Appareil autorisé.",
    "reactiver": "Appareil réactivé.",
    "bloquer": "Appareil bloqué : ses sessions ont été fermées.",
    "deconnecter": "Appareil déconnecté à distance.",
    "supprimer": "Appareil supprimé.",
}


def _executer(action: str, appareil_id: int, portee, acteur: dict, request: Request, admin: bool):
    courant = svc.appareil_courant(acteur["jti"])
    try:
        resultat = svc.agir(action, appareil_id, portee, courant, acteur["email"])
    except svc.AppareilIntrouvable:
        raise HTTPException(status_code=404, detail="Appareil introuvable.")
    except svc.ActionInterdite as e:
        raise HTTPException(status_code=400, detail=e.message)

    journaliser(
        _EVENEMENT[action],
        gravite="info" if action in ("autoriser", "reactiver") else "avertissement",
        succes=True, type_compte=acteur.get("type"), utilisateur_id=acteur.get("id"),
        email=resultat["email"] if admin else acteur.get("email"),
        entreprise_id=acteur.get("entrepriseId"), jti=acteur.get("jti"), request=request,
        acteur_email=acteur.get("email") if admin else None,
        details={"cible_id": appareil_id, "nb": resultat["sessionsFermees"]},
    )
    return {"message": _MESSAGE[action], "sessionsFermees": resultat["sessionsFermees"]}


# --- Mes appareils -----------------------------------------------------

@router.get("")
def lister_mes_appareils(utilisateur: dict = Depends(utilisateur_connecte)):
    courant = svc.appareil_courant(utilisateur["jti"])
    return {"appareils": svc.lister(svc.portee_compte(utilisateur), courant)}


@router.post("/{appareil_id}/{action}")
def agir_sur_mon_appareil(appareil_id: int, action: str, request: Request,
                          utilisateur: dict = Depends(utilisateur_connecte)):
    if action not in svc.ACTIONS:
        raise HTTPException(status_code=404, detail="Action inconnue.")
    return _executer(action, appareil_id, svc.portee_compte(utilisateur), utilisateur, request, False)


@router.delete("/{appareil_id}")
def supprimer_mon_appareil(appareil_id: int, request: Request,
                           utilisateur: dict = Depends(utilisateur_connecte)):
    return _executer("supprimer", appareil_id, svc.portee_compte(utilisateur), utilisateur, request, False)


# --- Administration (entreprise de l'administrateur uniquement) --------

def _entreprise_admin(admin: dict) -> str:
    if admin.get("entrepriseId") is None:
        raise HTTPException(status_code=403, detail="Action réservée à l'administrateur de l'entreprise.")
    return str(admin["entrepriseId"])


@router_admin.get("")
def lister_appareils_entreprise(admin: dict = Depends(exiger_role_admin)):
    _entreprise_admin(admin)
    courant = svc.appareil_courant(admin["jti"])
    return {"appareils": svc.lister(svc.portee_entreprise(admin), courant)}


@router_admin.post("/{appareil_id}/{action}")
def agir_sur_appareil_entreprise(appareil_id: int, action: str, request: Request,
                                 admin: dict = Depends(exiger_role_admin)):
    _entreprise_admin(admin)
    if action not in svc.ACTIONS:
        raise HTTPException(status_code=404, detail="Action inconnue.")
    return _executer(action, appareil_id, svc.portee_entreprise(admin), admin, request, True)


@router_admin.delete("/{appareil_id}")
def supprimer_appareil_entreprise(appareil_id: int, request: Request,
                                  admin: dict = Depends(exiger_role_admin)):
    _entreprise_admin(admin)
    return _executer("supprimer", appareil_id, svc.portee_entreprise(admin), admin, request, True)
