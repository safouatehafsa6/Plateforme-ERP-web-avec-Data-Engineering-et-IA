"""IDP -> modules : intégration d'un document VALIDÉ dans le module Achats.

Un document commercial validé (facture fournisseur, bon de commande, devis) devient un document
d'achat : le fournisseur et les produits sont rapprochés de ceux de l'entreprise (ou créés après
confirmation), puis un enregistrement `achat` est créé avec ses lignes, calculé par le moteur de
calcul centralisé (mêmes règles de TVA que les bons de commande saisis à la main).

Principes :
- l'humain décide : `proposer` ne modifie rien ; `integrer` n'écrit qu'après confirmation explicite
  de chaque ligne (produit existant ou à créer) et du fournisseur ;
- aucune intégration sans document validé ; un document ne s'intègre qu'UNE fois (verrou en base) ;
- tout se fait dans une seule transaction : en cas d'erreur, rien n'est créé ;
- traçabilité : le document d'origine, son numéro et son fichier sont notés dans l'achat, un lien
  `idp_integrations` relie les deux, et l'événement figure dans l'historique du document ;
- le stock n'est PAS modifié ici : il l'est par la réception, comme pour tout achat.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from datetime import datetime
from decimal import Decimal

from app.services import idp_stockage
from app.services.idp_controles import convertir_decimal

MODULE = "achats"
SEUIL_FOURNISSEUR = 0.88       # similarité minimale pour PROPOSER un fournisseur existant
SEUIL_PRODUIT = 0.90           # idem pour un produit
MOTS_FORME_JURIDIQUE = {
    "sarl", "sa", "sas", "sarlau", "snc", "scs", "ste", "societe", "company", "co", "ltd", "llc", "inc", "gmbh",
}

DDL_INTEGRATIONS = """
CREATE TABLE IF NOT EXISTS idp_integrations (
    id            SERIAL PRIMARY KEY,
    document_id   INTEGER NOT NULL REFERENCES idp_documents (id) ON DELETE CASCADE,
    module        TEXT NOT NULL,
    objet_type    TEXT NOT NULL,
    objet_id      INTEGER NOT NULL,
    objet_numero  TEXT,
    cree_par      TEXT,
    cree_le       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ux_idp_integration_document_module UNIQUE (document_id, module)
);
"""


class IntegrationErreur(Exception):
    """Erreur métier : `statut` est le code HTTP à renvoyer, `detail` un message pour l'utilisateur."""

    def __init__(self, statut: int, detail: str):
        super().__init__(detail)
        self.statut = statut
        self.detail = detail


# --------------------------------------------------------------------------
# Fonctions pures (testables sans base)
# --------------------------------------------------------------------------

def normaliser(texte, *, sans_forme_juridique: bool = False) -> str:
    t = unicodedata.normalize("NFD", str(texte or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    mots = re.sub(r"[^\w]+", " ", t).split()
    if sans_forme_juridique:
        mots = [m for m in mots if m not in MOTS_FORME_JURIDIQUE]
    return " ".join(mots)


def type_integrable(donnees: dict) -> tuple[str | None, str | None]:
    """Renvoie (type, raison_du_refus). type ∈ facture | bon_commande | devis."""
    brut = normaliser(donnees.get("type_document"))
    if not brut:
        return None, "Le type du document n'est pas précisé : corrigez-le (facture, bon de commande ou devis)."
    if "avoir" in brut or "credit" in brut:
        return None, "Les avoirs ne sont pas encore pris en charge par l'intégration automatique."
    if "facture" in brut or "invoice" in brut or "فاتوره" in brut or "فاتورة" in str(donnees.get("type_document")):
        return "facture", None
    if "commande" in brut or "purchase order" in brut:
        return "bon_commande", None
    if "devis" in brut or "quote" in brut or "proforma" in brut:
        return "devis", None
    return None, ("Ce type de document (« %s ») ne correspond à aucun document d'achat." % donnees.get("type_document"))


STATUT_ACHAT = {"facture": "facture", "bon_commande": "commande", "devis": "en_cours"}


def rapprocher_fournisseur(nom, fournisseurs: list[dict]) -> dict:
    """{'statut': 'trouve'|'suggere'|'a_creer', 'id', 'nom'} d'après le nom (forme juridique ignorée)."""
    cible = normaliser(nom, sans_forme_juridique=True)
    if not cible:
        return {"statut": "a_creer", "id": None, "nom": None}
    meilleur, score = None, 0.0
    for f in fournisseurs:
        candidat = normaliser(f["nom"], sans_forme_juridique=True)
        if candidat == cible:
            return {"statut": "trouve", "id": f["id"], "nom": f["nom"]}
        ratio = difflib.SequenceMatcher(None, cible, candidat).ratio()
        if ratio > score:
            meilleur, score = f, ratio
    if meilleur is not None and score >= SEUIL_FOURNISSEUR:
        return {"statut": "suggere", "id": meilleur["id"], "nom": meilleur["nom"]}
    return {"statut": "a_creer", "id": None, "nom": None}


def rapprocher_produit(designation, produits: list[dict]) -> dict:
    """Rapproche une désignation d'un produit : égalité du nom, référence citée, ou forte similarité."""
    cible = normaliser(designation)
    if not cible:
        return {"statut": "a_creer", "id": None, "reference": None, "nom": None}
    meilleur, score = None, 0.0
    for p in produits:
        nom = normaliser(p["nom"])
        reference = normaliser(p["reference"])
        if cible == nom:
            return {"statut": "trouve", "id": p["id"], "reference": p["reference"], "nom": p["nom"]}
        if reference and re.search(rf"(?<!\w){re.escape(reference)}(?!\w)", cible):
            return {"statut": "trouve", "id": p["id"], "reference": p["reference"], "nom": p["nom"]}
        ratio = difflib.SequenceMatcher(None, cible, nom).ratio()
        if ratio > score:
            meilleur, score = p, ratio
    if meilleur is not None and score >= SEUIL_PRODUIT:
        return {"statut": "suggere", "id": meilleur["id"], "reference": meilleur["reference"], "nom": meilleur["nom"]}
    return {"statut": "a_creer", "id": None, "reference": None, "nom": None}


def preparer_lignes(donnees: dict, produits: list[dict]) -> list[dict]:
    """Lignes du document prêtes pour l'achat, avec leurs problèmes éventuels (bloquants si non vides)."""
    lignes = []
    for index, brute in enumerate(donnees.get("lignes") or []):
        problemes = []
        designation = str(brute.get("designation") or "").strip()
        quantite = convertir_decimal(brute.get("quantite"))
        prix = convertir_decimal(brute.get("prix_unitaire"))
        remise = convertir_decimal(brute.get("remise_pct") if brute.get("remise_pct") is not None else brute.get("remise"))
        total = convertir_decimal(brute.get("total_ht") if brute.get("total_ht") is not None else brute.get("total"))
        taux = convertir_decimal(brute.get("taux_tva"))
        if not designation:
            problemes.append("Désignation absente.")
        if quantite is None or quantite <= 0:
            problemes.append("Quantité absente ou non positive.")
        elif quantite != quantite.to_integral_value():
            problemes.append("Quantité non entière : le module Achats n'accepte que des quantités entières.")
        if prix is None and total is not None and quantite not in (None, 0):
            prix = (total / quantite).quantize(Decimal("0.01"))
        if prix is None or prix < 0:
            problemes.append("Prix unitaire absent ou négatif.")
        if remise is None:
            remise = Decimal("0")
        if not Decimal("0") <= remise <= Decimal("100"):
            problemes.append("Remise hors de 0-100 %.")
        lignes.append({
            "index": index,
            "designation": designation[:150],
            "quantite": int(quantite) if quantite is not None and quantite == quantite.to_integral_value() else None,
            "prix_unitaire": format(prix, "f") if prix is not None else None,
            "remise_pct": format(remise, "f"),
            "taux_tva": format(taux, "f") if taux is not None else None,
            "produit": rapprocher_produit(designation, produits),
            "problemes": problemes,
        })
    return lignes


def valider_choix(lignes: list[dict], choix: dict, produits_ids: set[int]) -> list[dict]:
    """Associe chaque ligne à sa décision (produit existant ou création) ; refuse tout choix incomplet."""
    par_index = {c["index"]: c for c in choix.get("lignes", [])}
    resultat = []
    for ligne in lignes:
        if ligne["problemes"]:
            raise IntegrationErreur(
                400, f"Ligne {ligne['index'] + 1} : {' '.join(ligne['problemes'])} Corrigez le document avant l'intégration.")
        decision = par_index.get(ligne["index"])
        if decision is None:
            raise IntegrationErreur(400, f"Ligne {ligne['index'] + 1} : choisissez un produit existant ou la création.")
        if decision.get("creer"):
            resultat.append({**ligne, "produit_id": None, "creer": True})
        else:
            produit_id = decision.get("produit_id")
            if produit_id not in produits_ids:
                raise IntegrationErreur(400, f"Ligne {ligne['index'] + 1} : produit introuvable.")
            resultat.append({**ligne, "produit_id": produit_id, "creer": False})
    return resultat


# --------------------------------------------------------------------------
# Accès base
# --------------------------------------------------------------------------

def _assurer_table(cur) -> None:
    cur.execute(DDL_INTEGRATIONS)


def _dicts(cur) -> list[dict]:
    colonnes = [d[0] for d in cur.description]
    return [dict(zip(colonnes, ligne)) for ligne in cur.fetchall()]


def _verifier_eligible(document: dict) -> tuple[str | None, str | None]:
    if document["statut"] != "valide":
        return None, "Seul un document validé peut être intégré dans un module."
    donnees = document.get("donnees") or {}
    type_doc, raison = type_integrable(donnees)
    if raison:
        return None, raison
    if not donnees.get("lignes"):
        return None, "Le document ne contient aucune ligne d'article à intégrer."
    return type_doc, None


def proposer(pool, document_id: int) -> dict:
    """Ce que l'intégration ferait, sans rien écrire (à part la table de liens si elle n'existe pas)."""
    document = idp_stockage.obtenir(pool, document_id)
    with idp_stockage._transaction(pool) as cur:
        _assurer_table(cur)
        cur.execute("SELECT objet_id, objet_numero, cree_le FROM idp_integrations "
                    "WHERE document_id = %s AND module = %s", (document_id, MODULE))
        existant = cur.fetchone()
        if existant:
            return {"eligible": False, "deja_integre": {
                "module": MODULE, "id": existant[0], "numero": existant[1],
                "date": existant[2].isoformat() if hasattr(existant[2], "isoformat") else existant[2]}}
        type_doc, raison = _verifier_eligible(document)
        if raison:
            return {"eligible": False, "raison": raison}
        cur.execute("SELECT id, nom FROM fournisseur ORDER BY nom")
        fournisseurs = _dicts(cur)
        cur.execute("SELECT id, reference, nom FROM produit ORDER BY nom")
        produits = _dicts(cur)
    donnees = document["donnees"]
    nom_fournisseur = (donnees.get("fournisseur") or {}).get("nom") if isinstance(donnees.get("fournisseur"), dict) \
        else donnees.get("fournisseur")
    return {
        "eligible": True,
        "module": MODULE,
        "type_document": type_doc,
        "statut_cible": STATUT_ACHAT[type_doc],
        "fournisseur": {"nom_document": nom_fournisseur, **rapprocher_fournisseur(nom_fournisseur, fournisseurs)},
        "lignes": preparer_lignes(donnees, produits),
        "fournisseurs": fournisseurs,
        "produits": produits,
        "devise": donnees.get("devise"),
        "totaux": {"ht": donnees.get("total_ht"), "tva": donnees.get("total_tva"), "ttc": donnees.get("total_ttc")},
    }


def _reference_libre(cur, base: str) -> str:
    reference, n = base, 1
    while True:
        cur.execute("SELECT 1 FROM produit WHERE reference = %s", (reference,))
        if cur.fetchone() is None:
            return reference
        n += 1
        reference = f"{base}-{n}"


def integrer(pool, nom_base: str, document_id: int, choix: dict, acteur: str | None) -> dict:
    """Crée l'achat (et au besoin fournisseur / produits) à partir d'un document validé, en une transaction."""
    from app.services.moteur_regles_metier import assurer_schema, calculer_document

    idp_stockage.initialiser_schema(pool)
    assurer_schema(pool, nom_base)
    try:
        with idp_stockage._transaction(pool) as cur:
            _assurer_table(cur)
            document = idp_stockage._verrouiller(cur, document_id)      # verrou : une seule intégration à la fois
            cur.execute("SELECT objet_numero FROM idp_integrations WHERE document_id = %s AND module = %s",
                        (document_id, MODULE))
            deja = cur.fetchone()
            if deja:
                raise IntegrationErreur(409, f"Ce document est déjà intégré dans Achats ({deja[0]}).")
            type_doc, raison = _verifier_eligible(document)
            if raison:
                raise IntegrationErreur(409 if document["statut"] != "valide" else 400, raison)
            donnees = document["donnees"]

            cur.execute("SELECT id, reference, nom FROM produit")
            produits = _dicts(cur)
            lignes = valider_choix(preparer_lignes(donnees, produits), choix, {p["id"] for p in produits})

            # --- fournisseur ---
            fournisseur_id = choix.get("fournisseur_id")
            fournisseur_cree = False
            if fournisseur_id is not None:
                cur.execute("SELECT id FROM fournisseur WHERE id = %s", (fournisseur_id,))
                if cur.fetchone() is None:
                    raise IntegrationErreur(400, "Fournisseur introuvable.")
            elif choix.get("creer_fournisseur"):
                fiche = donnees.get("fournisseur") if isinstance(donnees.get("fournisseur"), dict) else {}
                nom = str(fiche.get("nom") or "").strip()[:150]
                if not nom:
                    raise IntegrationErreur(400, "Le nom du fournisseur est absent du document : choisissez un fournisseur existant.")
                cur.execute("INSERT INTO fournisseur (nom) VALUES (%s) RETURNING id", (nom,))
                fournisseur_id = cur.fetchone()[0]
                fournisseur_cree = True
            else:
                raise IntegrationErreur(400, "Choisissez un fournisseur existant ou la création du fournisseur.")

            # --- produits à créer ---
            produits_crees = 0
            for ligne in lignes:
                if ligne["creer"]:
                    reference = _reference_libre(cur, f"IDP-{document_id}-{ligne['index'] + 1}")
                    cur.execute(
                        "INSERT INTO produit (reference, nom, categorie, prix_unitaire, stock_actuel, taux_tva) "
                        "VALUES (%s, %s, %s, %s, 0, %s) RETURNING id",
                        (reference, ligne["designation"], "Importé par IDP", ligne["prix_unitaire"], ligne["taux_tva"]))
                    ligne["produit_id"] = cur.fetchone()[0]
                    produits_crees += 1

            # --- achat ---
            cur.execute("SELECT nextval('seq_achat_numero')")
            numero = f"ACH-{datetime.now().year}-{cur.fetchone()[0]:06d}"
            origine = (f"Créé depuis le document IDP n°{document_id} ({document.get('nom_fichier') or 'sans nom'})"
                       f" — {type_doc.replace('_', ' ')} n° {donnees.get('numero') or '?'}"
                       f" du {donnees.get('date') or '?'}")
            cur.execute(
                "INSERT INTO achat (fournisseur_id, statut, montant_total, numero, notes) "
                "VALUES (%s, %s, 0, %s, %s) RETURNING id",
                (fournisseur_id, STATUT_ACHAT[type_doc], numero, origine))
            achat_id = cur.fetchone()[0]
            cur.executemany(
                "INSERT INTO ligne_achat (achat_id, produit_id, quantite, prix_unitaire, remise_pct) "
                "VALUES (%s, %s, %s, %s, %s)",
                [(achat_id, l["produit_id"], l["quantite"], l["prix_unitaire"], l["remise_pct"]) for l in lignes])
            cur.execute(
                "SELECT la.produit_id, p.nom AS designation, la.quantite, la.prix_unitaire, la.remise_pct, p.taux_tva "
                "FROM ligne_achat la JOIN produit p ON p.id = la.produit_id WHERE la.achat_id = %s ORDER BY la.id",
                (achat_id,))
            lignes_calcul = _dicts(cur)
            resultat = calculer_document(cur, module="achats", type_document="bon_commande", document_id=achat_id,
                                         lignes=lignes_calcul, auteur=acteur or "", reference=numero)
            cur.execute("UPDATE achat SET montant_total = %s, montant_ht = %s, montant_tva = %s WHERE id = %s",
                        (resultat["montant_ttc"], resultat["montant_ht"], resultat["montant_tva"], achat_id))

            # --- traçabilité ---
            cur.execute(
                "INSERT INTO idp_integrations (document_id, module, objet_type, objet_id, objet_numero, cree_par) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (document_id, MODULE, "achat", achat_id, numero, acteur))
            idp_stockage._evenement(cur, document_id, "integration_achats", acteur, {
                "achat_id": achat_id, "numero": numero, "fournisseur_cree": fournisseur_cree,
                "produits_crees": produits_crees, "lignes": len(lignes)})
    except IntegrationErreur:
        raise
    except idp_stockage.DocumentIntrouvable as exc:
        raise IntegrationErreur(404, str(exc)) from exc
    except Exception as exc:
        if idp_stockage._est_violation_unicite(exc):
            raise IntegrationErreur(409, "Ce document vient d'être intégré par un autre utilisateur.") from exc
        raise
    return {
        "achat_id": achat_id, "numero": numero, "statut": STATUT_ACHAT[type_doc],
        "fournisseur_cree": fournisseur_cree, "produits_crees": produits_crees,
        "montant_ht": str(resultat["montant_ht"]), "montant_tva": str(resultat["montant_tva"]),
        "montant_ttc": str(resultat["montant_ttc"]),
        "message": f"Document intégré dans Achats : {numero}.",
    }
