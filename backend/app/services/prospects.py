"""Règles métier PURES du module Prospects (aucun accès base de données).

Isolées ici pour être testables sans PostgreSQL : normalisation des
coordonnées, détection de doublons, workflow des statuts, différences
entre deux versions d'une fiche.
"""
import re
import unicodedata
from difflib import SequenceMatcher

# --------------------------------------------------------------------------
# Statuts et workflow
# --------------------------------------------------------------------------
STATUTS = ("nouveau", "contacte", "qualifie", "perdu", "converti")

# « converti » n'est jamais choisi à la main : il résulte de la conversion.
TRANSITIONS = {
    "nouveau": {"contacte", "qualifie", "perdu"},
    "contacte": {"qualifie", "perdu"},
    "qualifie": {"contacte", "perdu"},
    "perdu": {"nouveau", "contacte"},
    "converti": set(),
}
STATUTS_CONVERTIBLES = {"nouveau", "contacte", "qualifie"}
SOURCES = ("site_web", "recommandation", "salon", "appel_entrant", "reseaux_sociaux", "campagne", "autre")
TYPES_SUIVI_MANUELS = ("appel", "email", "rendez_vous", "note", "relance")

CHAMPS_SURVEILLES = ("nom", "contact", "email", "telephone", "adresse", "source", "besoin", "responsable_id")


def transition_autorisee(actuel: str, cible: str) -> bool:
    return cible in TRANSITIONS.get(actuel, set())


def peut_etre_converti(statut: str, archive: bool) -> bool:
    return (not archive) and statut in STATUTS_CONVERTIBLES


# --------------------------------------------------------------------------
# Normalisation des coordonnées
# --------------------------------------------------------------------------
_MOTS_JURIDIQUES = {
    "sarl", "suarl", "sa", "sas", "sasu", "eurl", "ste", "societe", "ets", "etablissements",
    "ltd", "llc", "inc", "gmbh", "cie", "et",
}

SEUIL_NOM_SIMILAIRE = 0.88
LONGUEUR_CLE_TELEPHONE = 8


def normaliser_email(valeur) -> str | None:
    if not isinstance(valeur, str):
        return None
    valeur = valeur.strip().lower()
    return valeur or None


def chiffres_telephone(valeur) -> str:
    return "".join(c for c in (valeur or "") if c.isdigit())


def cle_telephone(valeur) -> str | None:
    """8 derniers chiffres : +216 12 345 678, 00216 12345678 et 12 345 678 donnent la même clé.

    Doit rester identique à l'index SQL ux_prospect_telephone (019_prospects.sql).
    """
    chiffres = chiffres_telephone(valeur)
    return chiffres[-LONGUEUR_CLE_TELEPHONE:] if chiffres else None


def _sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(c))


def normaliser_nom(valeur) -> str:
    """Minuscules, sans accents ni ponctuation, sans formes juridiques (SARL, STE...)."""
    if not isinstance(valeur, str):
        return ""
    # Les points sont supprimés (et non remplacés par un espace) pour que « S.A.R.L. » devienne « sarl ».
    texte = _sans_accents(valeur).lower().replace(".", "")
    texte = re.sub(r"[^a-z0-9]+", " ", texte)
    mots = [m for m in texte.split() if m not in _MOTS_JURIDIQUES]
    return " ".join(mots)


def mot_cle_nom(valeur) -> str | None:
    """Plus long mot (>= 3 lettres) du nom normalisé, utilisé pour présélectionner les candidats en SQL."""
    mots = [m for m in normaliser_nom(valeur).split() if len(m) >= 3]
    return max(mots, key=len) if mots else None


def similarite_noms(a, b) -> float:
    na, nb = normaliser_nom(a), normaliser_nom(b)
    if not na or not nb:
        return 0.0
    if na == nb or sorted(na.split()) == sorted(nb.split()):
        return 1.0
    # « Agence 1 » et « Agence 2 » sont deux entités distinctes : des nombres différents excluent la similarité.
    if set(re.findall(r"\d+", na)) != set(re.findall(r"\d+", nb)):
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


# --------------------------------------------------------------------------
# Détection de doublons
# --------------------------------------------------------------------------
def evaluer_candidat(candidat: dict, *, nom=None, email=None, telephone=None) -> dict | None:
    """Compare un enregistrement existant aux informations saisies.

    Niveau « fort » : même e-mail ou même téléphone (bloquant, non contournable).
    Niveau « possible » : nom identique ou très proche (à confirmer par l'utilisateur).
    Retourne None si aucun motif.
    """
    motifs = []
    email_n = normaliser_email(email)
    if email_n and normaliser_email(candidat.get("email")) == email_n:
        motifs.append("email")
    cle = cle_telephone(telephone)
    if cle and cle_telephone(candidat.get("telephone")) == cle:
        motifs.append("telephone")
    if nom:
        score = similarite_noms(nom, candidat.get("nom"))
        if score == 1.0:
            motifs.append("nom_identique")
        elif score >= SEUIL_NOM_SIMILAIRE:
            motifs.append("nom_similaire")
    if not motifs:
        return None
    resultat = dict(candidat)
    resultat["motifs"] = motifs
    resultat["niveau"] = "fort" if ("email" in motifs or "telephone" in motifs) else "possible"
    return resultat


def trier_doublons(doublons: list[dict]) -> list[dict]:
    return sorted(doublons, key=lambda d: (d["niveau"] != "fort", d.get("entite", ""), (d.get("nom") or "").lower(), d.get("id") or 0))


def contient_doublon_fort(doublons: list[dict]) -> bool:
    return any(d["niveau"] == "fort" for d in doublons)


def elever_nom_identique_client(doublons: list[dict]) -> list[dict]:
    """Règle déjà appliquée par la création de client : deux clients ne portent pas le même nom."""
    for d in doublons:
        if d.get("entite") == "client" and "nom_identique" in d["motifs"]:
            d["niveau"] = "fort"
    return doublons


MOTIFS_LIBELLES = {
    "email": "même adresse e-mail",
    "telephone": "même numéro de téléphone",
    "nom_identique": "même nom",
    "nom_similaire": "nom très proche",
}


def message_doublons(doublons: list[dict]) -> str:
    premier = doublons[0]
    nature = "client" if premier.get("entite") == "client" else "prospect"
    motifs = " et ".join(MOTIFS_LIBELLES[m] for m in premier["motifs"])
    suite = f" (et {len(doublons) - 1} autre(s))" if len(doublons) > 1 else ""
    archive = " archivé" if premier.get("archive") else ""
    return f"Doublon détecté : {nature}{archive} « {premier.get('nom')} » ({motifs}){suite}."


# --------------------------------------------------------------------------
# Différences entre deux versions d'une fiche
# --------------------------------------------------------------------------
def differences(avant: dict, apres: dict, champs=CHAMPS_SURVEILLES) -> dict:
    changements = {}
    for champ in champs:
        a, b = avant.get(champ), apres.get(champ)
        if (a or None) != (b or None):
            changements[champ] = {"avant": a, "apres": b}
    return changements
