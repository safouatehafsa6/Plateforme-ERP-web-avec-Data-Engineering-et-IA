"""Traitement intelligent de documents (IDP) - contrôles de cohérence.

Ces contrôles sont DÉTERMINISTES (aucune IA) : on ne fait jamais confiance
aveuglément à ce qu'un modèle de langage a extrait. Pour chaque document
structuré, on recalcule les montants et on signale les incohérences.

Format d'entrée attendu (les champs absents sont tolérés et signalés) :
{
  "type_document": "facture",            # facture | bon_commande | avoir | ...
  "numero": "F-2026-0042",
  "date": "2026-10-12",                  # ou 12/10/2026
  "date_echeance": "2026-11-12",
  "devise": "MAD",
  "fournisseur": {"nom": "...", "ice": "001234567000012"},
  "lignes": [{"designation": "...", "quantite": 2, "prix_unitaire": "100,00",
              "remise_pct": 0, "taux_tva": 20, "total_ht": 200}],
  "total_ht": 200, "total_tva": 40, "total_ttc": 240
}
Les montants peuvent être des nombres ou des textes ("1 234,56", "1.234,56").
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

TOLERANCE_ABSOLUE = Decimal("0.02")
TOLERANCE_RELATIVE = Decimal("0.001")          # 0,1 %
TAUX_TVA_MAROC = (0, 7, 10, 14, 20)
DEVISES_CONNUES = {
    "MAD", "EUR", "USD", "GBP", "CHF", "CAD", "AED", "SAR", "TND", "DZD",
    "XOF", "XAF", "EGP", "CNY", "JPY", "TRY",
}
FORMATS_DATE = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%y")


@dataclass
class Anomalie:
    code: str
    gravite: str            # "erreur" (bloque la validation) ou "avertissement"
    champ: str
    message: str
    attendu: str | None = None
    trouve: str | None = None

    def vers_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# Conversions tolérantes
# --------------------------------------------------------------------------

def convertir_decimal(valeur) -> Decimal | None:
    """Convertit un nombre ou un texte monétaire ; None si impossible."""
    if valeur is None or isinstance(valeur, bool):
        return None
    if isinstance(valeur, Decimal):
        return valeur
    if isinstance(valeur, (int, float)):
        return Decimal(str(valeur))

    texte = str(valeur).strip()
    if not texte:
        return None
    negatif = texte.startswith("(") and texte.endswith(")") or texte.startswith("-")
    texte = re.sub(r"[^\d.,]", "", texte)       # retire devise, espaces, signes
    if not texte or not re.search(r"\d", texte):
        return None

    if "," in texte and "." in texte:
        # Le dernier séparateur rencontré est le séparateur décimal.
        if texte.rfind(",") > texte.rfind("."):
            texte = texte.replace(".", "").replace(",", ".")
        else:
            texte = texte.replace(",", "")
    elif "," in texte:
        texte = texte.replace(",", ".")          # convention française / marocaine
    if texte.count(".") > 1:                      # ex. 1.234.567 -> séparateurs de milliers
        texte = texte.replace(".", "")
    try:
        nombre = Decimal(texte)
    except InvalidOperation:
        return None
    return -nombre if negatif else nombre


def convertir_date(valeur) -> date | None:
    if isinstance(valeur, datetime):
        return valeur.date()
    if isinstance(valeur, date):
        return valeur
    if not valeur:
        return None
    texte = str(valeur).strip()
    for format_date in FORMATS_DATE:
        try:
            return datetime.strptime(texte, format_date).date()
        except ValueError:
            continue
    return None


def _fmt(valeur: Decimal | None) -> str | None:
    return None if valeur is None else f"{valeur:.2f}"


def _ecart_significatif(attendu: Decimal, trouve: Decimal) -> bool:
    tolerance = max(TOLERANCE_ABSOLUE, abs(attendu) * TOLERANCE_RELATIVE)
    return abs(attendu - trouve) > tolerance


# --------------------------------------------------------------------------
# Contrôles
# --------------------------------------------------------------------------

def verifier_document(
    donnees: dict,
    *,
    aujourdhui: date | None = None,
    taux_tva_valides=TAUX_TVA_MAROC,
) -> list[Anomalie]:
    """Retourne la liste des anomalies détectées (vide = document cohérent)."""
    aujourdhui = aujourdhui or date.today()
    anomalies: list[Anomalie] = []
    ajouter = lambda *a, **k: anomalies.append(Anomalie(*a, **k))
    est_avoir = str(donnees.get("type_document", "")).lower() == "avoir"

    # --- Champs obligatoires ------------------------------------------------
    if not str(donnees.get("numero") or "").strip():
        ajouter("numero_manquant", "erreur", "numero", "Le numéro du document est absent.")

    fournisseur = donnees.get("fournisseur") or {}
    if not str((fournisseur.get("nom") if isinstance(fournisseur, dict) else fournisseur) or "").strip():
        ajouter("fournisseur_manquant", "erreur", "fournisseur.nom", "Le nom du fournisseur est absent.")
    elif isinstance(fournisseur, dict) and fournisseur.get("ice"):
        ice = re.sub(r"\s", "", str(fournisseur["ice"]))
        if not re.fullmatch(r"\d{15}", ice):
            ajouter("ice_invalide", "avertissement", "fournisseur.ice",
                    "L'ICE devrait comporter 15 chiffres.", "15 chiffres", ice)

    # --- Dates ----------------------------------------------------------------
    date_doc = convertir_date(donnees.get("date"))
    if not donnees.get("date"):
        ajouter("date_manquante", "erreur", "date", "La date du document est absente.")
    elif date_doc is None:
        ajouter("date_invalide", "erreur", "date", "La date du document n'est pas reconnue.",
                None, str(donnees.get("date")))
    else:
        if date_doc > aujourdhui + timedelta(days=1):
            ajouter("date_future", "avertissement", "date", "La date du document est dans le futur.",
                    f"<= {aujourdhui.isoformat()}", date_doc.isoformat())
        if date_doc < aujourdhui - timedelta(days=3650):
            ajouter("date_ancienne", "avertissement", "date", "La date du document a plus de 10 ans.",
                    None, date_doc.isoformat())

    if donnees.get("date_echeance"):
        echeance = convertir_date(donnees["date_echeance"])
        if echeance is None:
            ajouter("echeance_invalide", "avertissement", "date_echeance",
                    "La date d'échéance n'est pas reconnue.", None, str(donnees["date_echeance"]))
        elif date_doc and echeance < date_doc:
            ajouter("echeance_avant_date", "erreur", "date_echeance",
                    "L'échéance est antérieure à la date du document.",
                    f">= {date_doc.isoformat()}", echeance.isoformat())

    # --- Devise ---------------------------------------------------------------
    devise = str(donnees.get("devise") or "").strip().upper()
    if not devise:
        ajouter("devise_manquante", "avertissement", "devise", "La devise n'est pas indiquée.")
    elif devise not in DEVISES_CONNUES:
        ajouter("devise_inconnue", "avertissement", "devise", "Devise non reconnue.", None, devise)

    # --- Lignes ---------------------------------------------------------------
    lignes = donnees.get("lignes") or []
    if not lignes:
        ajouter("lignes_manquantes", "erreur", "lignes", "Aucune ligne d'article n'a été détectée.")

    somme_ht = Decimal("0")
    somme_tva = Decimal("0")
    tva_calculable = bool(lignes)
    for i, ligne in enumerate(lignes, start=1):
        champ = f"lignes[{i}]"
        quantite = convertir_decimal(ligne.get("quantite"))
        prix = convertir_decimal(ligne.get("prix_unitaire"))
        remise = convertir_decimal(ligne.get("remise_pct")) or Decimal("0")
        total_declare = convertir_decimal(ligne.get("total_ht"))
        taux = convertir_decimal(ligne.get("taux_tva"))

        if not str(ligne.get("designation") or "").strip():
            ajouter("designation_manquante", "avertissement", f"{champ}.designation",
                    f"Ligne {i} : désignation absente.")
        if quantite is not None and quantite <= 0 and not est_avoir:
            ajouter("quantite_invalide", "erreur", f"{champ}.quantite",
                    f"Ligne {i} : la quantité doit être positive.", "> 0", _fmt(quantite))
        if prix is not None and prix < 0 and not est_avoir:
            ajouter("prix_negatif", "avertissement", f"{champ}.prix_unitaire",
                    f"Ligne {i} : prix unitaire négatif.", ">= 0", _fmt(prix))
        if not Decimal("0") <= remise <= Decimal("100"):
            ajouter("remise_invalide", "erreur", f"{champ}.remise_pct",
                    f"Ligne {i} : la remise doit être comprise entre 0 et 100 %.", "0-100", _fmt(remise))

        calcule = None
        if quantite is not None and prix is not None:
            calcule = quantite * prix * (Decimal("1") - remise / Decimal("100"))
        if calcule is not None and total_declare is not None and _ecart_significatif(calcule, total_declare):
            ajouter("total_ligne_incoherent", "erreur", f"{champ}.total_ht",
                    f"Ligne {i} : le total HT ne correspond pas à quantité × prix.",
                    _fmt(calcule), _fmt(total_declare))

        total_ligne = total_declare if total_declare is not None else calcule
        if total_ligne is None:
            ajouter("ligne_incomplete", "avertissement", champ,
                    f"Ligne {i} : montant impossible à déterminer (quantité, prix ou total manquant).")
            tva_calculable = False
            continue
        somme_ht += total_ligne

        if taux is None:
            tva_calculable = False
        else:
            somme_tva += total_ligne * taux / Decimal("100")
            if taux_tva_valides and taux not in [Decimal(str(t)) for t in taux_tva_valides]:
                ajouter("taux_tva_inhabituel", "avertissement", f"{champ}.taux_tva",
                        f"Ligne {i} : taux de TVA inhabituel.",
                        "/".join(str(t) for t in taux_tva_valides), _fmt(taux))

    # --- Totaux ---------------------------------------------------------------
    total_ht = convertir_decimal(donnees.get("total_ht"))
    total_tva = convertir_decimal(donnees.get("total_tva"))
    total_ttc = convertir_decimal(donnees.get("total_ttc"))

    if total_ttc is None:
        ajouter("total_ttc_manquant", "erreur", "total_ttc", "Le total TTC est absent.")
    if lignes and total_ht is not None and _ecart_significatif(somme_ht, total_ht):
        ajouter("total_ht_incoherent", "erreur", "total_ht",
                "Le total HT ne correspond pas à la somme des lignes.", _fmt(somme_ht), _fmt(total_ht))
    if lignes and total_ht is None:
        ajouter("total_ht_manquant", "avertissement", "total_ht", "Le total HT est absent.")

    base_ht = total_ht if total_ht is not None else (somme_ht if lignes else None)
    if total_tva is not None and lignes and tva_calculable and _ecart_significatif(somme_tva, total_tva):
        ajouter("total_tva_incoherent", "erreur", "total_tva",
                "Le total de TVA ne correspond pas aux taux des lignes.", _fmt(somme_tva), _fmt(total_tva))
    if base_ht is not None and total_tva is not None and total_ttc is not None:
        if _ecart_significatif(base_ht + total_tva, total_ttc):
            ajouter("total_ttc_incoherent", "erreur", "total_ttc",
                    "Le total TTC ne correspond pas à HT + TVA.", _fmt(base_ht + total_tva), _fmt(total_ttc))
    elif base_ht is not None and total_tva is None and total_ttc is not None and base_ht > 0 and not est_avoir:
        taux_implicite = (total_ttc - base_ht) / base_ht * Decimal("100")
        if taux_tva_valides and all(abs(taux_implicite - Decimal(t)) > Decimal("0.5") for t in taux_tva_valides):
            ajouter("tva_implicite_inhabituelle", "avertissement", "total_ttc",
                    "L'écart entre TTC et HT ne correspond à aucun taux de TVA courant.",
                    "/".join(f"{t} %" for t in taux_tva_valides), f"{taux_implicite:.2f} %")

    return anomalies


def a_des_erreurs(anomalies: list[Anomalie]) -> bool:
    return any(a.gravite == "erreur" for a in anomalies)


def resume_anomalies(anomalies: list[Anomalie]) -> dict:
    return {
        "erreurs": sum(1 for a in anomalies if a.gravite == "erreur"),
        "avertissements": sum(1 for a in anomalies if a.gravite == "avertissement"),
    }


# --------------------------------------------------------------------------
# Détection de doublons
# --------------------------------------------------------------------------

def empreinte_document(donnees: dict) -> str | None:
    """Empreinte métier : même fournisseur + même numéro + même total TTC
    (+ même date) = même document, même si le fichier est différent
    (nouveau scan, autre format). None si le numéro ou le fournisseur manque."""
    fournisseur = donnees.get("fournisseur") or {}
    nom = fournisseur.get("nom") if isinstance(fournisseur, dict) else fournisseur
    numero = str(donnees.get("numero") or "").strip().lower()
    nom = re.sub(r"\s+", " ", str(nom or "")).strip().lower()
    if not numero or not nom:
        return None
    total = convertir_decimal(donnees.get("total_ttc"))
    date_doc = convertir_date(donnees.get("date"))
    cle = "|".join([nom, numero, _fmt(total) or "", date_doc.isoformat() if date_doc else ""])
    return hashlib.sha256(cle.encode("utf-8")).hexdigest()
