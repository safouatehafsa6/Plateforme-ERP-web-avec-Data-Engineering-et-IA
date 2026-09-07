import time

# Stockage en mémoire (suffisant pour une seule instance de serveur ; en
# production avec plusieurs instances, on utiliserait Redis pour partager
# l'état entre elles).

DUREE_VALIDITE_CAPTCHA_S = 5 * 60       # 5 minutes
FENETRE_BLOCAGE_S = 15 * 60             # 15 minutes
SEUIL_PROTECTION = 2                    # dès 2 échecs consécutifs, conformément à la demande

_captchas_actifs: dict[str, dict] = {}   # id -> {"code": str, "expiration": float}
_tentatives_par_email: dict[str, dict] = {}  # email -> {"echecs": int, "derniere": float}


def enregistrer_captcha(identifiant: str, code: str) -> None:
    _captchas_actifs[identifiant] = {"code": code, "expiration": time.time() + DUREE_VALIDITE_CAPTCHA_S}


def verifier_et_consommer_captcha(identifiant: str, valeur_saisie: str) -> bool:
    entree = _captchas_actifs.pop(identifiant, None)  # usage unique
    if not entree:
        return False
    if time.time() > entree["expiration"]:
        return False
    return entree["code"].upper() == (valeur_saisie or "").upper()


def etat_protection(email: str) -> dict:
    entree = _tentatives_par_email.get(email)
    if not entree:
        return {"echecs": 0, "protection_active": False}

    if time.time() - entree["derniere"] > FENETRE_BLOCAGE_S:
        _tentatives_par_email.pop(email, None)
        return {"echecs": 0, "protection_active": False}

    return {"echecs": entree["echecs"], "protection_active": entree["echecs"] >= SEUIL_PROTECTION}


def enregistrer_echec(email: str) -> None:
    actuel = _tentatives_par_email.get(email, {"echecs": 0})
    _tentatives_par_email[email] = {"echecs": actuel["echecs"] + 1, "derniere": time.time()}


def reinitialiser_tentatives(email: str) -> None:
    _tentatives_par_email.pop(email, None)
