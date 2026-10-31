"""Appareils connus d'un compte : enregistrement a la connexion, blocage,
autorisation, reactivation, suppression et deconnexion a distance.

Un appareil = un navigateur identifie par un identifiant aleatoire (en-tete
X-Appareil-Id, genere par l'interface). Seule l'empreinte SHA-256 est stockee.
Sans cet en-tete, l'empreinte est calculee a partir du User-Agent.

Mode strict (APPAREILS_MODE_STRICT=1) : un NOUVEL appareil d'un compte qui
en possede deja un est mis « en_attente » et ne peut pas se connecter tant
qu'il n'est pas autorise. Par defaut, un nouvel appareil est autorise mais
journalise (evenement « nouvel_appareil »). Un appareil « bloque » est
toujours refuse.
"""
import hashlib
import logging
import os
import re
from pathlib import Path

from app.db import pool_central
from app.security.audit import journaliser

_log = logging.getLogger("appareils")

_FORMAT_ID = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
FICHIER_SCHEMA = Path(__file__).resolve().parents[2] / "database" / "central" / "011_appareils.sql"


class AppareilRefuse(Exception):
    """Connexion refusee a cause de l'appareil (bloque ou en attente)."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class AppareilIntrouvable(Exception):
    pass


class ActionInterdite(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def mode_strict() -> bool:
    return os.getenv("APPAREILS_MODE_STRICT", "0") == "1"


def empreinte(request) -> str:
    brut = (request.headers.get("x-appareil-id") or "").strip()
    if _FORMAT_ID.match(brut):
        base = "id:" + brut
    else:
        base = "ua:" + (request.headers.get("user-agent") or "")[:300]
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def assurer_schema() -> None:
    """Cree la table des appareils si besoin (idempotent). Ne bloque jamais le demarrage."""
    try:
        sql = FICHIER_SCHEMA.read_text(encoding="utf-8")
        conn = pool_central.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
        finally:
            pool_central.putconn(conn)
    except Exception:
        _log.exception("Schema des appareils non applique au demarrage")


def _entreprise(claims: dict):
    valeur = claims.get("entrepriseId")
    return str(valeur) if valeur is not None else None


def enregistrer_connexion(claims: dict, request, info: dict, ip) -> dict:
    """Appelee a chaque connexion reussie (mot de passe valide). Retourne
    {"id", "nouveau"} ou leve AppareilRefuse."""
    type_compte = claims["type"]
    utilisateur_id = str(claims["id"])
    entreprise_id = _entreprise(claims)
    emp = empreinte(request)
    nom = "{} sur {}".format(info["navigateur"], info["systeme"])

    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",
                        ("appareil|{}|{}|{}".format(type_compte, utilisateur_id, entreprise_id),))
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM appareil WHERE type_compte = %s AND utilisateur_id = %s "
                "AND entreprise_id IS NOT DISTINCT FROM %s)",
                (type_compte, utilisateur_id, entreprise_id),
            )
            deja_un_appareil = bool(cur.fetchone()[0])
            statut_initial = (
                "en_attente" if (mode_strict() and deja_un_appareil and type_compte != "plateforme")
                else "autorise"
            )
            cur.execute(
                """
                INSERT INTO appareil
                    (type_compte, utilisateur_id, entreprise_id, email, empreinte, nom,
                     systeme, navigateur, type_appareil, derniere_ip, statut)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (type_compte, utilisateur_id, COALESCE(entreprise_id, ''), empreinte)
                DO UPDATE SET derniere_vue = NOW(), derniere_ip = EXCLUDED.derniere_ip,
                              email = EXCLUDED.email, nom = EXCLUDED.nom,
                              systeme = EXCLUDED.systeme, navigateur = EXCLUDED.navigateur,
                              type_appareil = EXCLUDED.type_appareil
                RETURNING id, statut, (xmax = 0)
                """,
                (type_compte, utilisateur_id, entreprise_id, claims["email"], emp, nom,
                 info["systeme"], info["navigateur"], info["appareil"], ip, statut_initial),
            )
            appareil_id, statut, insere = cur.fetchone()
        conn.commit()
    finally:
        pool_central.putconn(conn)

    commun = dict(type_compte=type_compte, utilisateur_id=utilisateur_id, email=claims["email"],
                  entreprise_id=entreprise_id, request=request)
    if statut == "bloque":
        journaliser("connexion_refusee", gravite="avertissement", succes=False,
                    details={"raison": "appareil_bloque"}, **commun)
        raise AppareilRefuse("Cet appareil a été bloqué. Contactez votre administrateur.")
    if statut == "en_attente":
        journaliser("appareil_en_attente", gravite="avertissement", succes=False,
                    details={"raison": "nouvel_appareil"}, **commun)
        raise AppareilRefuse(
            "Nouvel appareil détecté : il doit être autorisé par votre administrateur "
            "(ou depuis un appareil déjà connecté) avant de pouvoir se connecter."
        )
    return {"id": appareil_id, "nouveau": bool(insere) and deja_un_appareil}


# ---------------------------------------------------------------------
# Gestion (portee = clause SQL sur la table « appareil a » + parametres)
# ---------------------------------------------------------------------

COLONNES = (
    "a.id, a.email, a.type_compte, a.utilisateur_id, a.nom, a.systeme, a.navigateur, "
    "a.type_appareil, a.derniere_ip, a.statut, a.premiere_vue, a.derniere_vue, "
    "(SELECT COUNT(*) FROM session_utilisateur s WHERE s.appareil_id = a.id "
    "AND s.revoquee_le IS NULL AND s.expire_le > NOW())"
)
PORTEE_COMPTE = (
    "a.type_compte = %s AND a.utilisateur_id = %s AND a.entreprise_id IS NOT DISTINCT FROM %s"
)
PORTEE_ENTREPRISE = "a.entreprise_id = %s"


def portee_compte(utilisateur: dict):
    return PORTEE_COMPTE, (utilisateur["type"], str(utilisateur["id"]), _entreprise(utilisateur))


def portee_entreprise(admin: dict):
    return PORTEE_ENTREPRISE, (_entreprise(admin),)


def appareil_courant(jti: str):
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT appareil_id FROM session_utilisateur WHERE jti = %s", (jti,))
            ligne = cur.fetchone()
    finally:
        pool_central.putconn(conn)
    return ligne[0] if ligne else None


def _formater(l, courant) -> dict:
    return {
        "id": l[0], "email": l[1], "typeCompte": l[2], "utilisateurId": l[3], "nom": l[4],
        "systeme": l[5], "navigateur": l[6], "typeAppareil": l[7], "adresseIp": l[8],
        "statut": l[9], "premiereVue": l[10].isoformat(), "derniereVue": l[11].isoformat(),
        "sessionsActives": int(l[12]), "courant": l[0] == courant,
    }


def lister(portee: tuple, courant) -> list:
    clause, params = portee
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT {} FROM appareil a WHERE {} ORDER BY a.derniere_vue DESC".format(COLONNES, clause),
                params,
            )
            lignes = cur.fetchall()
    finally:
        pool_central.putconn(conn)
    return [_formater(l, courant) for l in lignes]


ACTIONS = ("autoriser", "reactiver", "bloquer", "deconnecter", "supprimer")
_MOTIFS = {"bloquer": "appareil_bloque", "deconnecter": "deconnexion_distance", "supprimer": "appareil_supprime"}


def agir(action: str, appareil_id: int, portee: tuple, courant, acteur_email: str) -> dict:
    """Applique une action. Retourne {"email", "sessionsFermees"}.
    Leve AppareilIntrouvable ou ActionInterdite."""
    if action not in ACTIONS:
        raise ActionInterdite("Action inconnue.")
    clause, params = portee
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT a.id, a.statut, a.email FROM appareil a WHERE a.id = %s AND ({}) FOR UPDATE".format(clause),
                (appareil_id,) + tuple(params),
            )
            ligne = cur.fetchone()
            if not ligne:
                conn.rollback()
                raise AppareilIntrouvable()
            _, statut, email = ligne

            if action in ("bloquer", "deconnecter", "supprimer") and appareil_id == courant:
                conn.rollback()
                raise ActionInterdite(
                    "Vous utilisez cet appareil : utilisez « Se déconnecter » plutôt que d'agir dessus."
                )
            if action == "autoriser" and statut != "en_attente":
                conn.rollback()
                raise ActionInterdite("Cet appareil n'est pas en attente d'autorisation.")
            if action == "reactiver" and statut != "bloque":
                conn.rollback()
                raise ActionInterdite("Cet appareil n'est pas bloqué.")

            fermees = 0
            if action in ("autoriser", "reactiver", "bloquer"):
                nouveau = "bloque" if action == "bloquer" else "autorise"
                cur.execute(
                    "UPDATE appareil SET statut = %s, statut_modifie_le = NOW(), statut_modifie_par = %s "
                    "WHERE id = %s",
                    (nouveau, acteur_email, appareil_id),
                )
            if action in _MOTIFS:
                cur.execute(
                    "UPDATE session_utilisateur SET revoquee_le = NOW(), motif_revocation = %s "
                    "WHERE appareil_id = %s AND revoquee_le IS NULL",
                    (_MOTIFS[action], appareil_id),
                )
                fermees = cur.rowcount
            if action == "supprimer":
                cur.execute("DELETE FROM appareil WHERE id = %s", (appareil_id,))
        conn.commit()
    finally:
        pool_central.putconn(conn)
    return {"email": email, "sessionsFermees": fermees}
