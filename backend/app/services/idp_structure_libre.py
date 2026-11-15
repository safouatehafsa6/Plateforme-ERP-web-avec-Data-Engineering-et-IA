"""IDP, étape 3 : structure LIBRE (champs, sections et tableaux découverts dans le document).

La première passe (idp_structuration) remplit le schéma fixe de la plateforme (facture : fournisseur,
lignes, totaux). Cette passe va plus loin : le modèle décrit TOUT ce que le document contient, avec
les champs qu'il découvre (parties, clauses, durées, références, obligations...), organisés en
sections typées. Rien n'y est limité aux champs codés en dur.

Garde-fous (le modèle ne décide jamais seul de ce qui entre dans la plateforme) :
- toute sortie est assainie en Python : clés normalisées, types en liste blanche, tailles bornées ;
- chaque valeur est contrôlée contre le texte réel du document : `verification` vaut
  `source_trouvee` (l'extrait cité existe dans le document), `valeur_trouvee` (la valeur y figure)
  ou `a_verifier` (aucune trace : probable invention) ;
- les montants, nombres et dates sont convertis par du code, pas par le modèle ;
- un champ absent du schéma standard est marqué `nouveau` : il est proposé à l'utilisateur, qui
  corrige puis valide ; seuls les champs d'un document VALIDÉ rejoignent le registre réutilisable
  (idp_stockage.enregistrer_champs_personnalises).
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Callable

from app.services.idp_controles import convertir_date, convertir_decimal

VERSION = 1
MODULES = (
    "documents", "ressources_humaines", "achats", "ventes",
    "comptabilite_fiscalite", "projets", "administration", "autre",
)
TYPES = ("texte", "nombre", "montant", "date", "booleen", "liste")
VERIFICATIONS = ("source_trouvee", "valeur_trouvee", "a_verifier", "corrige")

MAX_SECTIONS = 25
MAX_CHAMPS_PAR_SECTION = 60
MAX_TABLEAUX = 10
MAX_LIGNES_TABLEAU = 200
MAX_COLONNES = 20
MAX_RELATIONS = 60
MAX_TEXTE = 500
MAX_TEXTE_LONG = 2000

# Clés déjà portées par le schéma standard de la plateforme : tout le reste est « nouveau ».
CHAMPS_STANDARD = frozenset({
    "type_document", "numero", "date", "date_echeance", "devise", "total_ht", "total_tva",
    "total_ttc", "taux_tva", "fournisseur", "nom_fournisseur", "ice", "identifiant_fiscal",
})

CONSIGNES = (
    "Tu analyses un document professionnel (contrat, facture, bon de commande, rapport, formulaire, "
    "pièce administrative, document RH...) écrit en arabe, français ou anglais. Le texte du document "
    "est fourni entre les balises <document>.\n"
    "Décris TOUT ce qu'il contient d'utile sous forme de structure JSON, sans te limiter à une liste "
    "de champs connue d'avance. Ne recopie que ce qui est écrit : n'invente rien, ne devine rien. "
    "Si une information est absente, ne crée pas le champ.\n"
    "Réponds uniquement par un objet JSON de cette forme :\n"
    "{\"nature_document\": \"contrat de prestation | facture | ...\", \"langue\": \"fr|ar|en\", "
    "\"module_suggere\": \"documents|ressources_humaines|achats|ventes|comptabilite_fiscalite|projets|administration|autre\", "
    "\"resume\": \"2 phrases maximum\", "
    "\"sections\": [{\"cle\": \"parties\", \"nom\": \"Parties concernées\", \"champs\": ["
    "{\"cle\": \"client_nom\", \"libelle\": \"Nom du client\", \"type\": \"texte|nombre|montant|date|booleen|liste\", "
    "\"valeur\": \"...\", \"source\": \"extrait EXACT du document qui contient cette valeur\"}]}], "
    "\"tableaux\": [{\"cle\": \"lignes\", \"nom\": \"...\", \"colonnes\": [\"...\"], \"lignes\": [[\"...\"]]}], "
    "\"relations\": [{\"de\": \"section.cle_champ\", \"vers\": \"section.cle_champ\", \"nature\": \"engage | paie | concerne ...\"}]}\n"
    "Règles : sections adaptées à la nature du document (ex. contrat : parties, objet, durée, conditions "
    "financières, clauses, obligations, résiliation ; facture : émetteur, destinataire, paiement). "
    "Les clés sont en minuscules latines avec des underscores ; les libellés dans la langue du document. "
    "Montants et nombres écrits comme dans le document (sans symbole inventé). Dates telles qu'écrites."
)


# --------------------------------------------------------------------------
# Utilitaires de normalisation
# --------------------------------------------------------------------------

def _supprimer_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(c))


def normaliser_cle(texte: Any) -> str | None:
    """Clé stable : minuscules latines, chiffres et underscores (60 caractères maximum)."""
    if not isinstance(texte, str):
        return None
    cle = re.sub(r"[^a-z0-9]+", "_", _supprimer_accents(texte).lower()).strip("_")[:60]
    return cle or None


def _texte(valeur: Any, limite: int = MAX_TEXTE) -> str | None:
    if valeur is None or isinstance(valeur, (dict, list, bool)):
        return None
    texte = re.sub(r"\s+", " ", str(valeur)).strip()
    return texte[:limite] or None


def _recherche(texte: str) -> str:
    """Forme de comparaison : minuscules, sans accents latins, ponctuation et espaces écrasés.
    (Les lettres arabes sont conservées : \\w les reconnaît.)"""
    return re.sub(r"\W+", " ", _supprimer_accents(texte).lower()).strip()


def _present(extrait: str | None, doc_recherche: str) -> bool:
    """Vrai si l'extrait figure dans le document, en MOTS ENTIERS : sans cela, une valeur courte
    comme « 5 » serait « trouvée » dans « 2026 » ou « 12 500 » et validerait une invention."""
    forme = _recherche(extrait or "")
    return bool(forme) and f" {forme} " in f" {doc_recherche} "


def _verifier(valeur_texte: str | None, source: str | None, doc_recherche: str | None) -> str:
    if doc_recherche is None:
        return "corrige"
    if _present(source, doc_recherche):
        return "source_trouvee"
    if _present(valeur_texte, doc_recherche):
        return "valeur_trouvee"
    return "a_verifier"


def _convertir(type_champ: str, valeur: Any) -> tuple[Any, bool]:
    """Renvoie (valeur normalisée, conversion réussie). Les conversions sont faites en Python."""
    if type_champ in ("montant", "nombre"):
        nombre = convertir_decimal(valeur)
        return (format(nombre, "f"), True) if nombre is not None else (_texte(valeur), False)
    if type_champ == "date":
        jour = convertir_date(valeur)
        return (jour.isoformat(), True) if jour is not None else (_texte(valeur), False)
    if type_champ == "booleen":
        brut = str(valeur).strip().lower()
        if brut in ("oui", "yes", "true", "vrai", "1", "نعم"):
            return True, True
        if brut in ("non", "no", "false", "faux", "0", "لا"):
            return False, True
        return _texte(valeur), False
    if type_champ == "liste":
        elements = valeur if isinstance(valeur, list) else re.split(r"[;\n]", str(valeur or ""))
        liste = [t for t in (_texte(e) for e in elements) if t][:50]
        return liste, bool(liste)
    return _texte(valeur, MAX_TEXTE_LONG), True


# --------------------------------------------------------------------------
# Assainissement de la sortie du modèle
# --------------------------------------------------------------------------

def assainir(brut: Any, texte_document: str | None = None, champs_connus: set[str] | None = None) -> dict:
    """Transforme la réponse brute (ou une correction) en structure sûre et normalisée.

    `texte_document=None` : pas de contrôle contre le document (cas d'une correction humaine) ;
    la vérification vaut alors `corrige`.
    """
    if not isinstance(brut, dict):
        raise ValueError("La structure libre doit être un objet JSON.")
    champs_connus = champs_connus or set()
    doc_recherche = _recherche(texte_document) if texte_document is not None else None

    module = _texte(brut.get("module_suggere"), 40)
    module = normaliser_cle(module) if module else None
    resultat: dict = {
        "version": VERSION,
        "nature_document": _texte(brut.get("nature_document"), 120),
        "langue": _texte(brut.get("langue"), 8),
        "module_suggere": module if module in MODULES else "autre",
        "resume": _texte(brut.get("resume"), 600),
        "sections": [],
        "tableaux": [],
        "relations": [],
    }

    chemins: set[str] = set()
    sections_brutes = brut.get("sections") if isinstance(brut.get("sections"), list) else []
    cles_sections: set[str] = set()
    for index, section in enumerate(sections_brutes[:MAX_SECTIONS], 1):
        if not isinstance(section, dict):
            continue
        cle_section = normaliser_cle(section.get("cle")) or normaliser_cle(section.get("nom")) or f"section_{index}"
        while cle_section in cles_sections:
            cle_section += "_2"
        cles_sections.add(cle_section)
        champs: list[dict] = []
        cles_champs: set[str] = set()
        for numero, champ in enumerate((section.get("champs") if isinstance(section.get("champs"), list) else [])
                                       [:MAX_CHAMPS_PAR_SECTION], 1):
            if not isinstance(champ, dict):
                continue
            libelle = _texte(champ.get("libelle"), 120)
            cle = normaliser_cle(champ.get("cle")) or normaliser_cle(libelle) or f"champ_{numero}"
            while cle in cles_champs:
                cle += "_2"
            type_champ = champ.get("type") if champ.get("type") in TYPES else "texte"
            valeur_brute = champ.get("valeur")
            if valeur_brute is None or (isinstance(valeur_brute, str) and not valeur_brute.strip()):
                continue                                 # champ sans valeur : ignoré
            valeur, converti = _convertir(type_champ, valeur_brute)
            if valeur is None or valeur == "" or valeur == []:
                continue
            source = _texte(champ.get("source"), MAX_TEXTE_LONG)
            verification = _verifier(_texte(valeur_brute), source, doc_recherche)
            if not converti and verification != "corrige":
                verification = "a_verifier"              # « montant » illisible : on ne l'affirme pas
            cles_champs.add(cle)
            chemins.add(f"{cle_section}.{cle}")
            champs.append({
                "cle": cle,
                "libelle": libelle or cle.replace("_", " ").capitalize(),
                "type": type_champ,
                "valeur": valeur,
                "source": source,
                "verification": verification,
                "nouveau": cle not in CHAMPS_STANDARD and cle not in champs_connus,
                "origine": "utilisateur" if doc_recherche is None else "ia",
            })
        if champs:
            resultat["sections"].append({
                "cle": cle_section, "nom": _texte(section.get("nom"), 120) or cle_section.replace("_", " ").capitalize(),
                "champs": champs,
            })

    for index, tableau in enumerate((brut.get("tableaux") if isinstance(brut.get("tableaux"), list) else [])[:MAX_TABLEAUX], 1):
        if not isinstance(tableau, dict) or not isinstance(tableau.get("colonnes"), list):
            continue
        colonnes = [(_texte(c, 80) or f"colonne_{i}") for i, c in enumerate(tableau["colonnes"][:MAX_COLONNES], 1)]
        lignes = []
        for ligne in (tableau.get("lignes") if isinstance(tableau.get("lignes"), list) else [])[:MAX_LIGNES_TABLEAU]:
            if isinstance(ligne, list):
                cellules = [(_texte(c, 300) or "") for c in ligne[:len(colonnes)]]
                cellules += [""] * (len(colonnes) - len(cellules))
                if any(cellules):
                    lignes.append(cellules)
        if colonnes and lignes:
            resultat["tableaux"].append({
                "cle": normaliser_cle(tableau.get("cle")) or f"tableau_{index}",
                "nom": _texte(tableau.get("nom"), 120) or f"Tableau {index}",
                "colonnes": colonnes, "lignes": lignes,
            })

    for relation in (brut.get("relations") if isinstance(brut.get("relations"), list) else [])[:MAX_RELATIONS]:
        if not isinstance(relation, dict):
            continue
        de, vers = _texte(relation.get("de"), 130), _texte(relation.get("vers"), 130)
        if de in chemins and vers in chemins and de != vers:      # on ne garde que les liens vers des champs réels
            resultat["relations"].append({"de": de, "vers": vers, "nature": _texte(relation.get("nature"), 80) or "lié à"})
    return resultat


def _parser(brut: str | dict) -> dict:
    if isinstance(brut, dict):
        return brut
    texte = re.sub(r"^```(?:json)?\s*|\s*```$", "", (brut or "").strip(), flags=re.IGNORECASE)
    valeur = json.loads(texte)
    if not isinstance(valeur, dict):
        raise ValueError("La réponse du modèle n'est pas un objet JSON.")
    return valeur


def extraire(texte_document: str, appeler: Callable[[str], str | dict], champs_connus: set[str] | None = None) -> dict:
    """Appelle le modèle (via `appeler`) puis assainit sa réponse. Lève ValueError si inexploitable."""
    indice = ""
    if champs_connus:
        indice = ("\n\nChamps déjà connus de cette entreprise (réutilise exactement ces clés lorsqu'ils "
                  "correspondent) : " + ", ".join(sorted(champs_connus)[:60]))
    reponse = appeler(texte_document + indice)
    return assainir(_parser(reponse), texte_document, champs_connus)


# --------------------------------------------------------------------------
# Corrections humaines et registre des champs personnalisés
# --------------------------------------------------------------------------

def fusionner_correction(ancienne: dict | None, corrigee: Any, champs_connus: set[str] | None = None) -> dict:
    """Assainit la structure corrigée par l'utilisateur. Un champ dont la valeur a changé, ou qui
    est ajouté à la main, passe en `corrige` / origine `utilisateur` ; un champ intact garde sa
    vérification d'origine (la preuve dans le document ne disparaît pas)."""
    nouvelle = assainir(corrigee, None, champs_connus)
    anciens: dict[tuple, dict] = {}
    for section in (ancienne or {}).get("sections", []):
        for champ in section.get("champs", []):
            anciens[(section["cle"], champ["cle"])] = champ
    for section in nouvelle["sections"]:
        for champ in section["champs"]:
            avant = anciens.get((section["cle"], champ["cle"]))
            if avant and avant.get("valeur") == champ["valeur"]:
                champ["verification"] = avant.get("verification", "corrige")
                champ["origine"] = avant.get("origine", "ia")
                champ["source"] = champ["source"] or avant.get("source")
    return nouvelle


def champs_a_enregistrer(structure: dict | None) -> list[dict]:
    """Champs « nouveaux » d'un document validé, à verser au registre réutilisable."""
    if not structure:
        return []
    lignes = []
    for section in structure.get("sections", []):
        for champ in section.get("champs", []):
            if champ.get("nouveau") and champ.get("verification") != "a_verifier":
                lignes.append({
                    "cle": champ["cle"], "libelle": champ["libelle"], "type": champ["type"],
                    "section": section["nom"], "module": structure.get("module_suggere") or "autre",
                    "nature_document": structure.get("nature_document"),
                })
    return lignes
