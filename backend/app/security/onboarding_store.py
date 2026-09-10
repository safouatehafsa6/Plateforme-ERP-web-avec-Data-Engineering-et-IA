import time
import secrets

# Stockage en mémoire, même logique que pour les captchas/tentatives de
# connexion (voir security/protection.py). En production avec plusieurs
# instances du backend, on utiliserait Redis.

DUREE_VALIDITE_OTP_S = 10 * 60      # 10 minutes
MAX_TENTATIVES_OTP = 5              # nombre de mauvais codes autorisés avant blocage
DELAI_MIN_RENVOI_S = 60             # anti-abus : 1 minute entre deux renvois de code

_otp_par_entreprise: dict[int, dict] = {}
# entreprise_id -> {"code": str, "expiration": float, "tentatives": int, "dernier_envoi": float}

_admin_temp_par_entreprise: dict[int, dict] = {}  # entreprise_id -> {"nom", "email", "mot_de_passe_hash"}


def generer_et_stocker_otp(entreprise_id: int) -> str:
    """Génère un nouveau code et réinitialise le compteur de tentatives.
    Le code lui-même n'est JAMAIS retourné à l'appelant HTTP ni journalisé
    en clair — seul le module email_sender.py le manipule, pour l'envoyer
    par email (voir security des exigences de l'entreprise)."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    _otp_par_entreprise[entreprise_id] = {
        "code": code, "expiration": time.time() + DUREE_VALIDITE_OTP_S,
        "tentatives": 0, "dernier_envoi": time.time(),
    }
    return code


def peut_renvoyer_otp(entreprise_id: int) -> bool:
    entree = _otp_par_entreprise.get(entreprise_id)
    if not entree:
        return True
    return time.time() - entree["dernier_envoi"] >= DELAI_MIN_RENVOI_S


def secondes_avant_renvoi(entreprise_id: int) -> int:
    entree = _otp_par_entreprise.get(entreprise_id)
    if not entree:
        return 0
    restant = DELAI_MIN_RENVOI_S - (time.time() - entree["dernier_envoi"])
    return max(0, int(restant))


def verifier_otp(entreprise_id: int, code_saisi: str) -> tuple[bool, str]:
    """Retourne (succès, raison_échec). Bloque après trop de tentatives
    pour empêcher une attaque par force brute sur un code à 6 chiffres."""
    entree = _otp_par_entreprise.get(entreprise_id)
    if not entree:
        return False, "aucun_code_actif"

    if entree["tentatives"] >= MAX_TENTATIVES_OTP:
        return False, "trop_de_tentatives"

    if time.time() > entree["expiration"]:
        return False, "expire"

    if entree["code"] != code_saisi:
        entree["tentatives"] += 1
        return False, "code_incorrect"

    _otp_par_entreprise.pop(entreprise_id, None)
    return True, "ok"


def stocker_admin_temporaire(entreprise_id: int, nom: str, email: str, mot_de_passe_hash: str) -> None:
    _admin_temp_par_entreprise[entreprise_id] = {
        "nom": nom, "email": email, "mot_de_passe_hash": mot_de_passe_hash
    }


def recuperer_admin_temporaire(entreprise_id: int) -> dict | None:
    return _admin_temp_par_entreprise.get(entreprise_id)


def supprimer_admin_temporaire(entreprise_id: int) -> None:
    _admin_temp_par_entreprise.pop(entreprise_id, None)
