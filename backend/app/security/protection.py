import contextvars
import os
import time

from app.security import tentatives

# Stockage en mémoire (suffisant pour une seule instance de serveur ; en
# production avec plusieurs instances, on utiliserait Redis pour partager
# l'état entre elles).

DUREE_VALIDITE_CAPTCHA_S = 5 * 60       # 5 minutes
FENETRE_BLOCAGE_S = 15 * 60             # 15 minutes
SEUIL_PROTECTION = 2                    # dès 2 échecs consécutifs, conformément à la demande

_captchas_actifs: dict[str, dict] = {}   # id -> {"code": str, "expiration": float}
# Les compteurs d'echecs de connexion sont PERSISTANTS (voir security/tentatives.py).
# Verrouillage temporaire : un couple (email, adresse IP) est bloque apres
# SEUIL_VERROU_EMAIL_IP echecs, une adresse IP apres SEUIL_VERROU_IP echecs, pendant
# la fenetre de tentatives. Le couple email+IP evite qu'un tiers verrouille un compte
# depuis une autre adresse.
SEUIL_VERROU_EMAIL_IP = int(os.getenv("SEUIL_VERROU_EMAIL_IP", "10"))
SEUIL_VERROU_IP = int(os.getenv("SEUIL_VERROU_IP", "30"))

# Adresse IP de la requete en cours (renseignee par le login) : permet de
# compter les echecs par adresse sans changer la signature des fonctions.
ip_courante = contextvars.ContextVar("ip_courante", default=None)


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
    echecs, _ = tentatives.etat("email:" + email)
    return {"echecs": echecs, "protection_active": echecs >= SEUIL_PROTECTION}


def enregistrer_echec(email: str) -> None:
    tentatives.ajouter("email:" + email)
    ip = ip_courante.get()
    if ip:
        tentatives.ajouter("ei:{}|{}".format(email, ip))
        tentatives.ajouter("ip:" + ip)


def reinitialiser_tentatives(email: str) -> None:
    tentatives.reinitialiser("email:" + email)
    ip = ip_courante.get()
    if ip:
        tentatives.reinitialiser("ei:{}|{}".format(email, ip))


def verrouillage(email: str, ip) -> int:
    """Secondes restantes avant de pouvoir retenter (0 = pas verrouille)."""
    if not ip:
        return 0
    attentes = [0]
    echecs, reste = tentatives.etat("ei:{}|{}".format(email, ip))
    if echecs >= SEUIL_VERROU_EMAIL_IP:
        attentes.append(reste)
    echecs, reste = tentatives.etat("ip:" + ip)
    if echecs >= SEUIL_VERROU_IP:
        attentes.append(reste)
    return max(attentes)
