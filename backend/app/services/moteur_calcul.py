"""Moteur de calcul métier centralisé : calculs basés sur une période et un taux (%).

Formule :  Résultat = Montant × (Taux / 100) × (Nombre de jours / Base)      (Base = 365)

Ce module est volontairement indépendant de la base de données et de FastAPI :
tous les modules de la plateforme (RH, comptabilité, fiscalité, finance,
trésorerie, investissements, ventes, achats, contrats…) peuvent l'appeler
directement :

    from app.services.moteur_calcul import calculer_taux_unique, calculer_taux_variable

Convention de comptage des jours (paramètre ``inclure_dernier_jour``) :
  - False : jours = date_fin - date_debut            (ex. 18/02 -> 29/06/2026 = 131 jours)
  - True  : jours = date_fin - date_debut + 1        (les deux bornes sont comptées)
Les montants sont calculés avec des Decimal (jamais de float) et arrondis au centime
(arrondi commercial, 0,5 vers le haut). En mode « taux variables », le total est la somme
des résultats de chaque période (déjà arrondis) : le rapport s'additionne exactement.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENTIME = Decimal("0.01")
BASE_JOURS_DEFAUT = 365
MAX_JOURS = 366 * 100          # garde-fou : 100 ans
MAX_PERIODES = 500

# Modules pouvant utiliser le moteur (liste extensible : ajouter une entrée suffit).
MODULES_SOURCE = {
    "general": "Général",
    "ressources_humaines": "Ressources humaines",
    "comptabilite": "Comptabilité",
    "fiscalite": "Fiscalité",
    "finance": "Finance",
    "tresorerie": "Trésorerie",
    "investissements": "Investissements",
    "ventes": "Ventes",
    "achats": "Achats",
    "contrats": "Gestion des contrats",
    "autre": "Autre",
}


class ErreurCalcul(ValueError):
    """Erreur de saisie ou de règle de gestion (message destiné à l'utilisateur)."""


class LacuneTaux(ErreurCalcul):
    """Une partie de la période demandée n'est couverte par aucun taux de référence."""

    def __init__(self, lacunes: list[tuple[date, date]]):
        self.lacunes = lacunes
        texte = ", ".join(f"du {a:%d/%m/%Y} au {b:%d/%m/%Y}" for a, b in lacunes)
        super().__init__(f"Aucun taux de référence défini pour la période : {texte}.")


@dataclass(frozen=True)
class PeriodeTaux:
    """Une période du référentiel avec son taux (bornes incluses)."""
    date_debut: date
    date_fin: date
    taux: Decimal
    id: int | None = None


def arrondir(valeur: Decimal) -> Decimal:
    return valeur.quantize(CENTIME, rounding=ROUND_HALF_UP)


def _decimal(valeur, nom: str) -> Decimal:
    try:
        resultat = valeur if isinstance(valeur, Decimal) else Decimal(str(valeur))
    except (InvalidOperation, ValueError):
        raise ErreurCalcul(f"{nom} invalide.")
    if not resultat.is_finite():
        raise ErreurCalcul(f"{nom} invalide.")
    return resultat


def _valider_montant_taux(montant, taux=None):
    montant = _decimal(montant, "Montant")
    if montant <= 0:
        raise ErreurCalcul("Le montant doit être supérieur à 0.")
    if taux is None:
        return montant, None
    taux = _decimal(taux, "Taux")
    if taux < 0 or taux > 100:
        raise ErreurCalcul("Le taux doit être compris entre 0 et 100 %.")
    return montant, taux


def derniere_journee_comptee(date_fin: date, inclure_dernier_jour: bool) -> date:
    return date_fin if inclure_dernier_jour else date_fin - timedelta(days=1)


def nombre_jours(date_debut: date, date_fin: date, inclure_dernier_jour: bool = False) -> int:
    """Nombre de jours de la période selon la convention choisie."""
    if date_fin < date_debut:
        raise ErreurCalcul("La date de fin doit être postérieure ou égale à la date de début.")
    derniere = derniere_journee_comptee(date_fin, inclure_dernier_jour)
    if derniere < date_debut:
        raise ErreurCalcul(
            "La période ne contient aucun jour : la date de fin doit être postérieure à la date de début "
            "(ou cochez « inclure le dernier jour »)."
        )
    jours = (derniere - date_debut).days + 1
    if jours > MAX_JOURS:
        raise ErreurCalcul("La période est trop longue (100 ans maximum).")
    return jours


def resultat_periode(montant: Decimal, taux: Decimal, jours: int, base_jours: int = BASE_JOURS_DEFAUT) -> Decimal:
    """Montant × (Taux / 100) × (Jours / Base), arrondi au centime."""
    if base_jours <= 0:
        raise ErreurCalcul("La base de jours doit être positive.")
    return arrondir(montant * taux / Decimal(100) * Decimal(jours) / Decimal(base_jours))


def calculer_taux_unique(montant, date_debut: date, date_fin: date, taux,
                         *, inclure_dernier_jour: bool = False,
                         base_jours: int = BASE_JOURS_DEFAUT) -> dict:
    montant, taux = _valider_montant_taux(montant, taux)
    jours = nombre_jours(date_debut, date_fin, inclure_dernier_jour)
    resultat = resultat_periode(montant, taux, jours, base_jours)
    derniere = derniere_journee_comptee(date_fin, inclure_dernier_jour)
    return {
        "nombre_jours": jours,
        "resultat": resultat,
        "details": [{
            "debut": date_debut.isoformat(), "fin": derniere.isoformat(),
            "jours": jours, "taux": str(taux), "resultat": str(resultat), "periodeId": None,
        }],
    }


def decouper_periodes(date_debut: date, derniere_journee: date,
                      periodes: list[PeriodeTaux]) -> list[tuple[date, date, PeriodeTaux]]:
    """Découpe [date_debut, derniere_journee] selon les périodes de référence (bornes incluses).

    Lève LacuneTaux si une partie n'est couverte par aucune période. Les périodes de
    référence ne doivent pas se chevaucher (garanti par l'administration du référentiel).
    """
    morceaux, lacunes, curseur = [], [], date_debut
    pertinentes = sorted(
        (p for p in periodes if p.date_fin >= date_debut and p.date_debut <= derniere_journee),
        key=lambda p: (p.date_debut, p.date_fin),
    )
    for p in pertinentes:
        if curseur > derniere_journee:
            break
        if p.date_fin < curseur:
            continue
        if p.date_debut > curseur:
            lacunes.append((curseur, p.date_debut - timedelta(days=1)))
            curseur = p.date_debut
        fin_morceau = min(p.date_fin, derniere_journee)
        morceaux.append((curseur, fin_morceau, p))
        curseur = fin_morceau + timedelta(days=1)
    if curseur <= derniere_journee:
        lacunes.append((curseur, derniere_journee))
    if lacunes:
        raise LacuneTaux(lacunes)
    if len(morceaux) > MAX_PERIODES:
        raise ErreurCalcul("Trop de périodes à calculer.")
    return morceaux


def calculer_taux_variable(montant, date_debut: date, date_fin: date, periodes: list[PeriodeTaux],
                           *, inclure_dernier_jour: bool = True,
                           base_jours: int = BASE_JOURS_DEFAUT) -> dict:
    montant, _ = _valider_montant_taux(montant)
    jours_total = nombre_jours(date_debut, date_fin, inclure_dernier_jour)
    derniere = derniere_journee_comptee(date_fin, inclure_dernier_jour)
    if not periodes:
        raise ErreurCalcul("Le référentiel ne contient aucune période de taux.")
    details, total = [], Decimal("0.00")
    for debut, fin, p in decouper_periodes(date_debut, derniere, periodes):
        jours = (fin - debut).days + 1
        res = resultat_periode(montant, p.taux, jours, base_jours)
        total += res
        details.append({
            "debut": debut.isoformat(), "fin": fin.isoformat(), "jours": jours,
            "taux": str(p.taux), "resultat": str(res), "periodeId": p.id,
        })
    return {"nombre_jours": jours_total, "resultat": total, "details": details}
