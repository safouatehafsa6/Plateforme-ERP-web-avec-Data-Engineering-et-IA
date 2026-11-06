"""Montants en toutes lettres : français, anglais, arabe ; MAD, EUR, USD.

    montant_en_lettres("1234.50", "MAD", "fr")
    -> "mille deux cent trente-quatre dirhams et cinquante centimes"

Principes :
- Les montants sont traités en Decimal (jamais en float), arrondis au centime
  (demi supérieur). Une chaîne "1 234,50" ou "1234.50" est acceptée.
- Plage : 0 à 999 999 999 999,99 (en valeur absolue). Au-delà : ValueError.
- Aucune dépendance externe.

Conventions :
- Français : orthographe traditionnelle (soixante-dix, quatre-vingts), traits
  d'union entre dizaines et unités, « et » pour 21, 31, 41, 51, 61, 71,
  « cent » et « vingt » prennent un s quand rien ne les suit (« deux cents
  dirhams », « deux cent mille »), « un million de dirhams ».
- Anglais : variante américaine, sans « and » à l'intérieur du nombre
  (« one hundred twenty-three »), « and » avant les centimes.
- Arabe : arabe standard, nombre au nominatif, accord du nom de la devise
  selon la règle du nombre (1 et 2 : singulier ou duel, 3 à 10 : pluriel,
  11 à 99 : singulier accusatif, centaines : singulier génitif).
  À faire relire par un arabophone avant diffusion à des clients.

Pour ajouter une devise : une entrée dans DEVISES (noms fr, en, ar), rien
d'autre.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

LANGUES = ("fr", "en", "ar")
LIMITE_EXCLUE = 10 ** 12

LIBELLES = {
    "fr": "Montant en lettres",
    "en": "Amount in words",
    "ar": "المبلغ بالحروف",
}

_ALIAS_DEVISES = {
    "DH": "MAD", "DHS": "MAD", "DIRHAM": "MAD",
    "€": "EUR", "EURO": "EUR",
    "$": "USD", "US$": "USD", "DOLLAR": "USD",
}


# --------------------------------------------------------------------------
# Devises
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class FormesAr:
    """Formes d'un nom compté en arabe."""
    bare: str      # singulier nu (génitif) : مائة درهم
    un: str        # exactement un : درهم واحد
    duel: str      # exactement deux : درهمان
    plur: str      # 3 à 10 : ثلاثة دراهم
    acc: str       # 11 à 99 : أحد عشر درهماً
    duel_c: str = ""   # duel en annexion (échelles seulement) : ألفا


@dataclass(frozen=True)
class Devise:
    code: str
    fr: tuple   # (unité sing., unité plur., sous-unité sing., sous-unité plur.)
    en: tuple
    ar: tuple   # (FormesAr unité, FormesAr sous-unité)


DEVISES = {
    "MAD": Devise(
        "MAD",
        fr=("dirham", "dirhams", "centime", "centimes"),
        en=("dirham", "dirhams", "centime", "centimes"),
        ar=(FormesAr("درهم", "درهم واحد", "درهمان", "دراهم", "درهماً"),
            FormesAr("سنتيم", "سنتيم واحد", "سنتيمان", "سنتيمات", "سنتيماً")),
    ),
    "EUR": Devise(
        "EUR",
        fr=("euro", "euros", "centime", "centimes"),
        en=("euro", "euros", "cent", "cents"),
        ar=(FormesAr("يورو", "يورو واحد", "اثنان يورو", "يورو", "يورو"),
            FormesAr("سنت", "سنت واحد", "سنتان", "سنتات", "سنتاً")),
    ),
    "USD": Devise(
        "USD",
        fr=("dollar américain", "dollars américains", "cent", "cents"),
        en=("dollar", "dollars", "cent", "cents"),
        ar=(FormesAr("دولار", "دولار واحد", "دولاران", "دولارات", "دولاراً"),
            FormesAr("سنت", "سنت واحد", "سنتان", "سنتات", "سنتاً")),
    ),
}

_ECHELLES_AR = (
    (10 ** 9, FormesAr("مليار", "مليار", "ملياران", "مليارات", "ملياراً", "مليارا")),
    (10 ** 6, FormesAr("مليون", "مليون", "مليونان", "ملايين", "مليوناً", "مليونا")),
    (10 ** 3, FormesAr("ألف", "ألف", "ألفان", "آلاف", "ألفاً", "ألفا")),
)


# --------------------------------------------------------------------------
# Entrées
# --------------------------------------------------------------------------

def normaliser_langue(langue: str) -> str:
    code = str(langue or "").strip().lower().replace("_", "-").split("-")[0]
    if code not in LANGUES:
        raise ValueError(f"Langue non prise en charge : {langue!r} (fr, en, ar).")
    return code


def normaliser_devise(devise: str) -> Devise:
    brut = str(devise or "").strip().upper()
    code = _ALIAS_DEVISES.get(brut, brut)
    if code not in DEVISES:
        raise ValueError(
            f"Devise non prise en charge : {devise!r} ({', '.join(sorted(DEVISES))}).")
    return DEVISES[code]


def normaliser_montant(montant) -> Decimal:
    """Decimal arrondi au centime, borné. Refuse les booléens, NaN, l'infini."""
    if isinstance(montant, bool):
        raise ValueError("Montant invalide.")
    if isinstance(montant, Decimal):
        valeur = montant
    elif isinstance(montant, (int, float)):
        valeur = Decimal(str(montant))
    elif isinstance(montant, str):
        texte = "".join(montant.split()).replace(" ", "").replace(" ", "")
        if "," in texte and "." not in texte:
            texte = texte.replace(",", ".")
        try:
            valeur = Decimal(texte)
        except InvalidOperation:
            raise ValueError("Montant invalide.") from None
    else:
        raise ValueError("Montant invalide.")
    if not valeur.is_finite():
        raise ValueError("Montant invalide.")
    if abs(valeur) >= LIMITE_EXCLUE:      # avant quantize, qui échoue sur les très grands nombres
        raise ValueError("Montant trop grand (maximum 999 999 999 999,99).")
    try:
        valeur = valeur.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ValueError("Montant invalide.") from None
    if abs(valeur) >= LIMITE_EXCLUE:      # 999 999 999 999,996 arrondi à 10^12
        raise ValueError("Montant trop grand (maximum 999 999 999 999,99).")
    return valeur


def _decouper(valeur: Decimal) -> tuple[bool, int, int]:
    negatif = valeur < 0
    centimes = int(abs(valeur) * 100)
    return negatif, centimes // 100, centimes % 100


def _groupes(n: int) -> list[tuple[int, int]]:
    """[(milliards, 10**9), (millions, 10**6), (milliers, 10**3)] non nuls, puis
    le reste (0..999) sous la clé 1."""
    resultat = []
    for taille, _ in _ECHELLES_AR:
        compte, n = divmod(n, taille)
        if compte:
            resultat.append((compte, taille))
    if n:
        resultat.append((n, 1))
    return resultat


# --------------------------------------------------------------------------
# Français
# --------------------------------------------------------------------------

_FR_UNITES = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit",
              "neuf", "dix", "onze", "douze", "treize", "quatorze", "quinze", "seize"]
_FR_DIZAINES = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}


def _fr_moins_de_100(n: int, final: bool) -> str:
    if n < 17:
        return _FR_UNITES[n]
    if n < 20:
        return "dix-" + _FR_UNITES[n - 10]
    if n < 70:
        base, unite = _FR_DIZAINES[n // 10], n % 10
        if unite == 0:
            return base
        return base + (" et un" if unite == 1 else "-" + _FR_UNITES[unite])
    if n < 80:                                    # 70 à 79 : soixante + 10 à 19
        return "soixante et onze" if n == 71 else "soixante-" + _fr_moins_de_100(n - 60, final)
    if n == 80:
        return "quatre-vingts" if final else "quatre-vingt"
    return "quatre-vingt-" + _fr_moins_de_100(n - 80, final)


def _fr_moins_de_1000(n: int, final: bool) -> str:
    """`final` : rien ne suit le nombre qui exigerait de laisser cent/vingt
    invariables (donc « deux cents » mais « deux cent mille »)."""
    centaines, reste = divmod(n, 100)
    if centaines == 0:
        return _fr_moins_de_100(reste, final)
    if centaines == 1:
        debut = "cent"
    else:
        debut = _FR_UNITES[centaines] + " cent" + ("s" if reste == 0 and final else "")
    return debut if reste == 0 else debut + " " + _fr_moins_de_100(reste, final)


def _nombre_fr(n: int) -> str:
    if n == 0:
        return "zéro"
    noms = {10 ** 9: "milliard", 10 ** 6: "million"}
    parties = []
    for compte, taille in _groupes(n):
        if taille in noms:
            parties.append(_fr_moins_de_1000(compte, True) + " " + noms[taille]
                           + ("s" if compte > 1 else ""))
        elif taille == 1000:
            parties.append("mille" if compte == 1 else _fr_moins_de_1000(compte, False) + " mille")
        else:
            parties.append(_fr_moins_de_1000(compte, True))
    return " ".join(parties)


# --------------------------------------------------------------------------
# Anglais
# --------------------------------------------------------------------------

_EN_UNITES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
              "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
              "sixteen", "seventeen", "eighteen", "nineteen"]
_EN_DIZAINES = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty", 6: "sixty",
                7: "seventy", 8: "eighty", 9: "ninety"}


def _en_moins_de_100(n: int) -> str:
    if n < 20:
        return _EN_UNITES[n]
    base, unite = _EN_DIZAINES[n // 10], n % 10
    return base if unite == 0 else base + "-" + _EN_UNITES[unite]


def _en_moins_de_1000(n: int) -> str:
    centaines, reste = divmod(n, 100)
    if centaines == 0:
        return _en_moins_de_100(reste)
    debut = _EN_UNITES[centaines] + " hundred"
    return debut if reste == 0 else debut + " " + _en_moins_de_100(reste)


def _nombre_en(n: int) -> str:
    if n == 0:
        return "zero"
    noms = {10 ** 9: " billion", 10 ** 6: " million", 10 ** 3: " thousand", 1: ""}
    return " ".join(_en_moins_de_1000(compte) + noms[taille] for compte, taille in _groupes(n))


# --------------------------------------------------------------------------
# Arabe
# --------------------------------------------------------------------------

_AR_UNITES = ["", "واحد", "اثنان", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية",
              "تسعة", "عشرة"]
_AR_ONZE_A_DIX_NEUF = {11: "أحد عشر", 12: "اثنا عشر", 13: "ثلاثة عشر", 14: "أربعة عشر",
                       15: "خمسة عشر", 16: "ستة عشر", 17: "سبعة عشر", 18: "ثمانية عشر",
                       19: "تسعة عشر"}
_AR_DIZAINES = {2: "عشرون", 3: "ثلاثون", 4: "أربعون", 5: "خمسون", 6: "ستون",
                7: "سبعون", 8: "ثمانون", 9: "تسعون"}
_AR_CENTAINES = {1: "مائة", 2: "مائتان", 3: "ثلاثمائة", 4: "أربعمائة", 5: "خمسمائة",
                 6: "ستمائة", 7: "سبعمائة", 8: "ثمانمائة", 9: "تسعمائة"}


def _ar_moins_de_100(n: int) -> str:
    if n <= 10:
        return _AR_UNITES[n]
    if n < 20:
        return _AR_ONZE_A_DIX_NEUF[n]
    dizaine, unite = divmod(n, 10)
    return _AR_DIZAINES[dizaine] if unite == 0 else _AR_UNITES[unite] + " و" + _AR_DIZAINES[dizaine]


def _ar_mots(n: int) -> str:
    """Nombre de 1 à 999 en toutes lettres (nominatif)."""
    centaines, reste = divmod(n, 100)
    if centaines == 0:
        return _ar_moins_de_100(reste)
    return _AR_CENTAINES[centaines] if reste == 0 else (
        _AR_CENTAINES[centaines] + " و" + _ar_moins_de_100(reste))


def _ar_compte(n: int, formes: FormesAr, annexion: bool = False, elider: bool = False) -> str:
    """`n` (1..999) suivi du nom compté. `annexion` : le nom de la devise suit
    immédiatement (« ألفا درهم », « ثلاثة آلاف درهم »). `elider` : pour 101, 102,
    201... on écrit « مائة ودرهم واحد » plutôt que « مائة درهم ودرهم واحد »."""
    if n == 1:
        return formes.bare if annexion else formes.un
    if n == 2:
        return formes.duel_c if annexion else formes.duel
    reste = n % 100
    if reste == 0:                       # centaines pleines : singulier génitif
        mots = "مائتا" if n == 200 else _AR_CENTAINES[n // 100]
        return mots + " " + formes.bare
    if reste in (1, 2) and n > 100:      # « مائة ألف وألف » : on scinde
        debut = (_AR_CENTAINES[(n - reste) // 100] if elider
                 else _ar_compte(n - reste, formes, annexion))
        return debut + " و" + _ar_compte(reste, formes, annexion)
    if 3 <= reste <= 10:
        return _ar_mots(n) + " " + formes.plur
    return _ar_mots(n) + " " + (formes.bare if annexion else formes.acc)


def _ar_nombre_avec_nom(n: int, nom: FormesAr | None) -> str:
    """Entier positif en arabe ; avec `nom`, accorde ce nom (devise)."""
    parties = []
    groupes = _groupes(n)
    reste_nul = not groupes or groupes[-1][1] != 1
    for rang, (compte, taille) in enumerate(groupes):
        if taille == 1:
            parties.append(_ar_compte(compte, nom, elider=True) if nom else _ar_mots(compte))
            continue
        formes = dict(_ECHELLES_AR)[taille]
        dernier = rang == len(groupes) - 1
        parties.append(_ar_compte(compte, formes, annexion=bool(nom and dernier and reste_nul)))
    texte = " و".join(parties)
    if nom and reste_nul:
        texte += " " + nom.bare
    return texte


def _nombre_ar(n: int) -> str:
    return "صفر" if n == 0 else _ar_nombre_avec_nom(n, None)


# --------------------------------------------------------------------------
# API publique
# --------------------------------------------------------------------------

def nombre_en_lettres(n: int, langue: str = "fr") -> str:
    """Entier de 0 à 999 999 999 999 en toutes lettres (sans devise)."""
    if isinstance(n, bool) or not isinstance(n, int) or not 0 <= n < LIMITE_EXCLUE:
        raise ValueError("Entier attendu entre 0 et 999 999 999 999.")
    return {"fr": _nombre_fr, "en": _nombre_en, "ar": _nombre_ar}[normaliser_langue(langue)](n)


def _voyelle(mot: str) -> bool:
    return mot[:1].lower() in "aeiouéèêhàâîôû"


def montant_en_lettres(montant, devise: str = "MAD", langue: str = "fr") -> str:
    valeur = normaliser_montant(montant)
    langue = normaliser_langue(langue)
    devise_ = normaliser_devise(devise)
    negatif, entier, centimes = _decouper(valeur)
    if entier == 0 and centimes == 0:
        negatif = False

    if langue == "ar":
        noms_u, noms_s = devise_.ar
        parties = []
        if entier or not centimes:
            parties.append("صفر " + noms_u.bare if entier == 0 else _ar_nombre_avec_nom(entier, noms_u))
        if centimes:
            parties.append(_ar_nombre_avec_nom(centimes, noms_s))
        texte = " و".join(parties)
        return ("سالب " if negatif else "") + texte

    nombre = _nombre_fr if langue == "fr" else _nombre_en
    u_sing, u_plur, s_sing, s_plur = getattr(devise_, langue)
    parties = []
    if entier or not centimes:
        if langue == "fr":
            pluriel = entier >= 2
            liaison = ""
            if entier and entier % 10 ** 6 == 0:    # « un million de dirhams »
                nom = u_plur if pluriel else u_sing
                liaison = " d'" if _voyelle(nom) else " de "
                parties.append(nombre(entier) + liaison + nom)
            else:
                parties.append(nombre(entier) + " " + (u_plur if pluriel else u_sing))
        else:
            parties.append(nombre(entier) + " " + (u_sing if entier == 1 else u_plur))
    if centimes:
        parties.append(nombre(centimes) + " " + (s_sing if centimes == 1 else s_plur))
    texte = (" et " if langue == "fr" else " and ").join(parties)
    if negatif:
        texte = ("moins " if langue == "fr" else "minus ") + texte
    return texte


def libelle_montant_en_lettres(langue: str = "fr") -> str:
    return LIBELLES[normaliser_langue(langue)]
