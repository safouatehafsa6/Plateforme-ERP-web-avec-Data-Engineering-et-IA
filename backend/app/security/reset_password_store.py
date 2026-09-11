import time
import secrets

# Même principe que pour l'OTP d'inscription (onboarding_store.py), mais
# indexé par email plutôt que par entreprise_id, car la réinitialisation
# peut concerner un Super Administrateur ou un utilisateur d'entreprise.

DUREE_VALIDITE_OTP_S = 10 * 60
MAX_TENTATIVES_OTP = 5
DELAI_MIN_RENVOI_S = 60

_otp_par_email: dict[str, dict] = {}


def generer_et_stocker_otp(email: str) -> str:
    code = f"{secrets.randbelow(1_000_000):06d}"
    _otp_par_email[email] = {
        "code": code, "expiration": time.time() + DUREE_VALIDITE_OTP_S,
        "tentatives": 0, "dernier_envoi": time.time(), "verifie": False,
    }
    return code


def peut_renvoyer(email: str) -> bool:
    entree = _otp_par_email.get(email)
    if not entree:
        return True
    return time.time() - entree["dernier_envoi"] >= DELAI_MIN_RENVOI_S


def verifier_otp(email: str, code_saisi: str) -> tuple[bool, str]:
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

    # On marque le code comme vérifié mais on ne le supprime pas encore :
    # l'étape finale (nouveau mot de passe) revérifie ce statut, pour
    # éviter qu'un code déjà consommé une fois ne puisse resservir.
    entree["verifie"] = True
    return True, "ok"


def code_deja_verifie(email: str) -> bool:
    entree = _otp_par_email.get(email)
    return bool(entree and entree.get("verifie") and time.time() <= entree["expiration"])


def supprimer(email: str) -> None:
    _otp_par_email.pop(email, None)
