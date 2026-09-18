"""
password_reset_store.py — Stockage en mémoire du parcours "Mot de passe
oublié" : code OTP envoyé par email, puis jeton de réinitialisation à
usage unique une fois le code validé.

Même logique que security/onboarding_store.py (utilisé pour la
vérification email lors de l'inscription), mais indexé par email plutôt
que par entreprise_id, et avec un jeton intermédiaire supplémentaire :
une fois le code OTP vérifié, on émet un jeton de réinitialisation à
usage unique, exigé pour l'étape finale (changement du mot de passe).
Cela empêche un appel direct à /reinitialiser-mot-de-passe sans être
passé par la vérification du code.

En production avec plusieurs instances du backend, on utiliserait Redis
pour partager cet état entre elles.
"""

import time
import secrets

DUREE_VALIDITE_OTP_S = 10 * 60          # 10 minutes
MAX_TENTATIVES_OTP = 5                  # mauvais codes autorisés avant blocage
DELAI_MIN_RENVOI_S = 60                 # anti-abus : 1 minute entre deux renvois
DUREE_VALIDITE_JETON_RESET_S = 10 * 60  # le jeton de réinitialisation expire aussi après 10 min

_otp_par_email: dict[str, dict] = {}
# email -> {"code": str, "expiration": float, "tentatives": int, "dernier_envoi": float}

_jetons_reset_par_email: dict[str, dict] = {}
# email -> {"jeton": str, "expiration": float}


def generer_et_stocker_otp(email: str) -> str:
    """Génère un nouveau code et réinitialise le compteur de tentatives.
    Le code n'est jamais retourné à l'appelant HTTP ni journalisé en
    clair — seul email_sender.py le manipule pour l'envoyer par email."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    _otp_par_email[email] = {
        "code": code, "expiration": time.time() + DUREE_VALIDITE_OTP_S,
        "tentatives": 0, "dernier_envoi": time.time(),
    }
    # Toute demande de nouveau code invalide un éventuel jeton de reset
    # déjà émis pour cet email (on repart du début du parcours).
    _jetons_reset_par_email.pop(email, None)
    return code


def peut_renvoyer_otp(email: str) -> bool:
    entree = _otp_par_email.get(email)
    if not entree:
        return True
    return time.time() - entree["dernier_envoi"] >= DELAI_MIN_RENVOI_S


def secondes_avant_renvoi(email: str) -> int:
    entree = _otp_par_email.get(email)
    if not entree:
        return 0
    restant = DELAI_MIN_RENVOI_S - (time.time() - entree["dernier_envoi"])
    return max(0, int(restant))


def verifier_otp(email: str, code_saisi: str) -> tuple[bool, str]:
    """Retourne (succès, raison_échec). Bloque après trop de tentatives
    pour empêcher une attaque par force brute sur un code à 6 chiffres.
    En cas de succès, émet un jeton de réinitialisation à usage unique."""
    entree = _otp_par_email.get(email)
    if not entree:
        return False, "aucun_code_actif"

    if entree["tentatives"] >= MAX_TENTATIVES_OTP:
        return False, "trop_de_tentatives"

    if time.time() > entree["expiration"]:
        return False, "expire"

    if entree["code"] != code_saisi:
        entree["tentatives"] += 1
        return False, "code_incorrect"

    _otp_par_email.pop(email, None)
    _jetons_reset_par_email[email] = {
        "jeton": secrets.token_urlsafe(32),
        "expiration": time.time() + DUREE_VALIDITE_JETON_RESET_S,
    }
    return True, "ok"


def obtenir_jeton_reset(email: str) -> str | None:
    entree = _jetons_reset_par_email.get(email)
    return entree["jeton"] if entree else None


def verifier_et_consommer_jeton_reset(email: str, jeton: str) -> bool:
    """Usage unique : le jeton est supprimé qu'il soit valide ou non,
    pour empêcher toute réutilisation après un changement de mot de
    passe réussi (ou une tentative échouée avec un mauvais jeton)."""
    entree = _jetons_reset_par_email.pop(email, None)
    if not entree:
        return False
    if time.time() > entree["expiration"]:
        return False
    return secrets.compare_digest(entree["jeton"], jeton or "")
