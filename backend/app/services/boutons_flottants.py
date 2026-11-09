"""Règles PURES des boutons flottants (aucun accès base) : listes autorisées, validation, valeurs par défaut.

Tout ce que l'administrateur peut saisir est validé ici ET par des contraintes CHECK en base : un lien
`javascript:`, une couleur ou une icône inconnues ne peuvent jamais atteindre l'écran des utilisateurs.
"""
import re

ICONES = (
    "bell", "bot", "headset", "message-circle", "log-in", "user-plus", "moon", "globe", "phone", "mail",
    "help-circle", "info", "star", "heart", "shopping-cart", "file-text", "calculator", "video", "users",
    "settings", "calendar", "zap", "gift", "megaphone", "book-open", "life-buoy", "link", "external-link",
    "home", "search", "sparkles", "credit-card", "shield-check", "bookmark",
)
ACTIONS_INTEGREES = ("assistant", "notifications", "support", "theme", "langue")
ACTIONS = ACTIONS_INTEGREES + ("route", "url", "whatsapp")
TAILLES = ("petit", "moyen", "grand")
PLACEMENTS = ("menu", "libre")
POSITIONS = ("bas-droite", "bas-gauche", "milieu-droite", "milieu-gauche", "haut-droite", "haut-gauche")
POSITIONS_PRINCIPAL = ("auto",) + POSITIONS          # « auto » : en bas, côté fin de la langue (droite, ou gauche en arabe)
AUDIENCES = ("public", "connecte", "tous")
PROFILS = ("plateforme", "admin_entreprise", "interne", "externe")
APPAREILS = ("tous", "mobile", "ordinateur")
LANGUES = ("fr", "en", "ar")

_RE_COULEUR = re.compile(r"^#[0-9a-fA-F]{6}$")
_RE_CLE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,38}$")
_RE_ROUTE = re.compile(r"^/[A-Za-z0-9_\-/.]*(\?[A-Za-z0-9_\-=&%.]*)?(#[A-Za-z0-9_\-]*)?$")
_RE_PREFIXE = re.compile(r"^/[A-Za-z0-9_\-/]*$")
_RE_URL = re.compile(r"^(https://[^\s/$.?#][^\s]*|mailto:[^\s@]+@[^\s@]+\.[^\s@]{2,}|tel:\+?[0-9]{6,15})$", re.IGNORECASE)
_RE_NUMERO = re.compile(r"^[0-9]{6,15}$")


def generer_cle(texte: str) -> str:
    """Identifiant technique à partir d'un titre : « Promo Été ! » → « promo-ete »."""
    import unicodedata
    base = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:38]
    return base if _RE_CLE.match(base) else "bouton"


def couleur_valide(valeur) -> bool:
    return valeur is None or bool(_RE_COULEUR.match(valeur))


def cle_valide(valeur) -> bool:
    return bool(_RE_CLE.match(valeur or ""))


def verifier_cible(action: str, cible, nouvel_onglet: bool = False) -> str | None:
    """Retourne None si la cible est cohérente avec l'action, sinon un message d'erreur."""
    cible = (cible or "").strip() or None
    if action in ACTIONS_INTEGREES:
        return "Cette action intégrée n'accepte aucune cible." if cible else None
    if action == "route":
        if not cible:
            return "Indiquez la page interne (ex. /clients)."
        if len(cible) > 200 or cible.startswith("//") or ".." in cible or not _RE_ROUTE.match(cible):
            return "Chemin interne invalide : il doit commencer par « / » (ex. /clients)."
        return "L'ouverture dans un nouvel onglet ne concerne que les liens externes." if nouvel_onglet else None
    if action == "url":
        if not cible:
            return "Indiquez l'adresse du lien."
        if len(cible) > 500 or not _RE_URL.match(cible):
            return "Lien invalide : seuls https://, mailto: et tel: sont acceptés."
        return None
    if action == "whatsapp":
        if cible is None:
            return None            # numéro de la configuration de la plateforme (VITE_WHATSAPP_NUMBER)
        chiffres = re.sub(r"[\s+().-]", "", cible)
        return None if _RE_NUMERO.match(chiffres) else "Numéro WhatsApp invalide (6 à 15 chiffres, indicatif inclus)."
    return "Action inconnue."


def normaliser_cible(action: str, cible):
    cible = (cible or "").strip() or None
    if action == "whatsapp" and cible:
        return re.sub(r"[\s+().-]", "", cible)
    return None if action in ACTIONS_INTEGREES else cible


def verifier_prefixes(valeurs) -> str | None:
    if len(valeurs) > 20:
        return "20 pages maximum par liste."
    for v in valeurs:
        if len(v) > 100 or not _RE_PREFIXE.match(v) or ".." in v:
            return f"Page invalide « {v} » : utilisez un préfixe comme /clients."
    return None


def _t(fr, en, ar):
    return {"fr": fr, "en": en, "ar": ar}


# Réplique exacte du menu d'aide d'origine : sans configuration, l'interface est inchangée.
DEFAUTS_SYSTEME = (
    dict(cle="notifications", titres=_t("Notifications", "Notifications", "الإشعارات"), icone="bell", action="notifications", audience="connecte", ordre=10),
    dict(cle="assistant", titres=_t("Assistant IA", "AI Assistant", "مساعد الذكاء الاصطناعي"), icone="bot", action="assistant", audience="connecte", ordre=20),
    dict(cle="support", titres=_t("Assistance / Contact", "Support / Contact", "الدعم / التواصل"), icone="headset", action="support", audience="tous", ordre=30),
    dict(cle="whatsapp", titres=_t("WhatsApp", "WhatsApp", "واتساب"), icone="message-circle", action="whatsapp", audience="tous", ordre=40, nouvel_onglet=True),
    dict(cle="connexion", titres=_t("Connexion", "Sign in", "تسجيل الدخول"), icone="log-in", action="route", cible="/", audience="public", ordre=50),
    dict(cle="inscription", titres=_t("Créer un compte", "Create account", "إنشاء حساب"), icone="user-plus", action="route", cible="/inscription", audience="public", ordre=60),
    dict(cle="theme", titres=_t("Mode sombre / clair", "Dark / light mode", "الوضع الداكن / الفاتح"), icone="moon", action="theme", audience="tous", ordre=90),
    dict(cle="langue", titres=_t("Langue", "Language", "اللغة"), icone="globe", action="langue", audience="tous", ordre=100),
)
CONFIG_PAR_DEFAUT = dict(actif=True, position="auto", taille="moyen", couleur=None, icone="headset")
