"""Saisie intelligente : suggestions de mots, d'expressions et de termes métier dès les premières lettres.

Logique pure (sans base de données ni réseau), donc rapide et testable. Elle combine :
  - un glossaire métier trilingue (français / English / العربية) : on tape dans une langue,
    la suggestion indique les équivalents dans les deux autres ;
  - le catalogue réel de l'entreprise (clients, fournisseurs, produits), fourni par le routeur.
Le contexte joue sur le classement : le module affiché favorise les entités correspondantes,
et la langue de l'utilisateur favorise le glossaire dans cette langue.
"""
from __future__ import annotations

import re
import unicodedata

# (fr, en, ar)
GLOSSAIRE = [
    ("facture", "invoice", "فاتورة"),
    ("devis", "quote", "عرض سعر"),
    ("commande", "order", "طلب"),
    ("bon de commande", "purchase order", "أمر شراء"),
    ("bon de livraison", "delivery note", "وصل التسليم"),
    ("client", "customer", "زبون"),
    ("fournisseur", "supplier", "مورد"),
    ("produit", "product", "منتج"),
    ("stock", "stock", "مخزون"),
    ("rupture de stock", "stockout", "نفاد المخزون"),
    ("inventaire", "inventory", "جرد"),
    ("livraison", "delivery", "تسليم"),
    ("paiement", "payment", "أداء"),
    ("échéance", "due date", "تاريخ الاستحقاق"),
    ("avoir", "credit note", "إشعار دائن"),
    ("remise", "discount", "تخفيض"),
    ("TVA", "VAT", "ضريبة القيمة المضافة"),
    ("chiffre d'affaires", "revenue", "رقم المعاملات"),
    ("marge", "margin", "هامش الربح"),
    ("solde", "balance", "رصيد"),
    ("retard de paiement", "late payment", "تأخر الأداء"),
    ("quantité", "quantity", "كمية"),
    ("prix unitaire", "unit price", "ثمن الوحدة"),
    ("synthèse des ventes", "sales summary", "ملخص المبيعات"),
    ("produits les plus vendus", "top products", "أكثر المنتجات مبيعا"),
    ("meilleurs clients", "top customers", "أفضل الزبناء"),
    ("comptabilité", "accounting", "محاسبة"),
    ("rapport", "report", "تقرير"),
    ("procédure interne", "internal procedure", "المسطرة الداخلية"),
    ("politique de l'entreprise", "company policy", "سياسة الشركة"),
]

LANGUES = ("fr", "en", "ar")
# Modules de l'application -> type d'entité favorisé
MODULE_VERS_TYPE = {
    "clients": "client", "ventes": "client", "facturation": "client",
    "fournisseurs": "fournisseur", "achats": "fournisseur",
    "stock": "produit",
}
MIN_CARACTERES = 2
MAX_MOTS = 3


def normaliser(texte: str | None) -> str:
    """Minuscules, sans accents ni diacritiques arabes, formes d'alef/ya unifiées."""
    texte = (texte or "").lower().replace("’", "'")
    texte = "".join(c for c in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(c))
    texte = re.sub(r"[\u0640\u064b-\u065f\u0670]", "", texte)  # tatweel + tashkeel
    texte = re.sub(r"[أإآٱ]", "ا", texte).replace("ى", "ي").replace("ة", "ه")
    return " ".join(texte.split())


def _suffixes(saisie: str):
    """Fragments finaux de la saisie, du plus long (3 mots) au plus court (1 mot), avec le texte d'origine."""
    mots = saisie.rstrip().split(" ")
    if saisie != saisie.rstrip():  # espace final : pas de fragment en cours de frappe
        return
    for n in range(min(MAX_MOTS, len(mots)), 0, -1):
        brut = " ".join(mots[-n:])
        yield brut, normaliser(brut)


def suggerer(saisie: str, catalogue: list[dict], langue: str = "fr", module: str | None = None, limite: int = 6) -> list[dict]:
    """Retourne des suggestions [{texte, remplace, type, detail}] pour la fin de `saisie`.

    `catalogue` : [{"texte": "Société Atlas", "type": "client", "detail": "…"}, ...]
    `remplace` : le fragment de la saisie que la suggestion remplace.
    """
    saisie = saisie or ""
    if len(normaliser(saisie)) < MIN_CARACTERES:
        return []
    type_favorise = MODULE_VERS_TYPE.get(module or "")
    resultats: dict[str, tuple[float, dict]] = {}

    def ajouter(score, item):
        cle = (item["type"], normaliser(item["texte"]))
        if cle not in resultats or resultats[cle][0] < score:
            resultats[cle] = (score, item)

    candidats = [{"texte": t[i], "type": "terme", "langue": LANGUES[i],
                  "detail": " · ".join(t[j] for j in range(3) if j != i)}
                 for t in GLOSSAIRE for i in range(3)] + list(catalogue)

    for brut, frag in _suffixes(saisie):
        if len(frag) < MIN_CARACTERES:
            continue
        # un fragment plus long (donc plus précis) est prioritaire sur un fragment plus court
        bonus_longueur = 0.5 * len(frag.split())
        for cand in candidats:
            norm = normaliser(cand["texte"])
            if norm == frag:
                continue  # déjà saisi en entier
            if norm.startswith(frag):
                score = 3.0
            elif frag.split()[-1:] and len(frag.split()) == 1 and any(m.startswith(frag) for m in norm.split()[1:]):
                score = 1.5  # début d'un mot interne (ex. « atlas » dans « Société Atlas »)
            else:
                continue
            if cand["type"] == "terme":
                score += 0.4 if cand.get("langue") == langue else 0
            elif cand["type"] == type_favorise:
                score += 0.6
            ajouter(score + bonus_longueur, {
                "texte": cand["texte"], "remplace": brut, "type": cand["type"], "detail": cand.get("detail", ""),
            })

    classes = sorted(resultats.values(), key=lambda x: (-x[0], len(x[1]["texte"]), x[1]["texte"]))
    return [item for _, item in classes[:limite]]
