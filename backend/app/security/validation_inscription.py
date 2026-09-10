"""
validation_inscription.py — Règles de validation appliquées côté Backend
lors de l'inscription, conformément au principe rappelé par l'entreprise :
« Ne jamais faire confiance uniquement aux données provenant du Frontend. »

Toutes ces règles sont déjà vérifiées côté frontend pour l'expérience
utilisateur (retour immédiat), mais DOIVENT être revérifiées ici, car un
appel direct à l'API pourrait contourner le formulaire.
"""

import re

# Regex volontairement stricte mais raisonnable : présence d'un @, d'un
# domaine avec au moins un point, aucun espace toléré nulle part.
REGEX_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

# Téléphone : chiffres, espaces, +, - autorisés, 8 à 15 chiffres au total.
REGEX_TELEPHONE = re.compile(r"^[+]?[\d\s\-]{8,20}$")


def valider_email(email: str, confirmation: str) -> str | None:
    """Retourne un message d'erreur, ou None si tout est valide."""
    if email != email.strip():
        return "L'adresse email ne doit contenir aucun espace en début ou fin."
    if " " in email:
        return "L'adresse email ne doit contenir aucun espace."
    if not REGEX_EMAIL.match(email):
        return "Le format de l'adresse email est invalide."
    if email.lower() != (confirmation or "").strip().lower():
        return "Les deux adresses email ne correspondent pas."
    return None


def valider_mot_de_passe(mot_de_passe: str, confirmation: str) -> str | None:
    if len(mot_de_passe) < 8:
        return "Le mot de passe doit contenir au moins 8 caractères."
    if not re.search(r"[A-Za-z]", mot_de_passe):
        return "Le mot de passe doit contenir au moins une lettre."
    if not re.search(r"\d", mot_de_passe):
        return "Le mot de passe doit contenir au moins un chiffre."
    if not re.search(r"[^\w\s]", mot_de_passe):
        return "Le mot de passe doit contenir au moins un caractère spécial."
    if mot_de_passe != confirmation:
        return "Les deux mots de passe ne correspondent pas."
    return None


def valider_telephone(telephone: str | None) -> str | None:
    if not telephone:
        return None  # champ optionnel
    if not REGEX_TELEPHONE.match(telephone):
        return "Le format du numéro de téléphone est invalide."
    return None


def calculer_force_mot_de_passe(mot_de_passe: str) -> str:
    """Utilisé uniquement pour renvoyer une indication au frontend si
    besoin d'une double vérification ; le frontend calcule aussi son
    propre indicateur en temps réel pour l'affichage immédiat."""
    score = 0
    if len(mot_de_passe) >= 8:
        score += 1
    if len(mot_de_passe) >= 12:
        score += 1
    if re.search(r"[A-Z]", mot_de_passe):
        score += 1
    if re.search(r"\d", mot_de_passe):
        score += 1
    if re.search(r"[^\w\s]", mot_de_passe):
        score += 1

    if score <= 2:
        return "faible"
    if score <= 4:
        return "moyen"
    return "fort"
