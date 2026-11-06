"""Detection des connexions inhabituelles et alertes de securite.

Apres chaque connexion REUSSIE, on compare avec l'historique du compte
(sessions conservees 30 jours) :
  - nouvel_appareil            : appareil jamais vu pour ce compte ;
  - nouvelle_adresse_ip        : adresse IP jamais utilisee par ce compte ;
  - nouveau_systeme            : systeme d'exploitation jamais utilise ;
  - apres_echecs_repetes       : 3 echecs ou plus dans les 15 dernieres minutes.
Une connexion qui declenche au moins une regle est journalisee
(« connexion_inhabituelle »), notifiee a la personne et a l'administrateur de
son entreprise, et signalee par email. Rien ici ne bloque ni ne retarde la
connexion : toutes les erreurs sont absorbees.
"""
import logging
import os
import threading
from datetime import datetime

from app.db import get_pool_entreprise, pool_central
from app.security.audit import journaliser

_log = logging.getLogger("alertes")

SEUIL_ECHECS = 3
FENETRE_ECHECS_MIN = 15

LIBELLES = {
    "nouvel_appareil": "un appareil jamais utilisé auparavant",
    "nouvelle_adresse_ip": "une adresse IP jamais utilisée auparavant",
    "nouveau_systeme": "un système d'exploitation jamais utilisé auparavant",
    "apres_echecs_repetes": "après plusieurs tentatives de connexion échouées",
}


def evaluer(claims: dict, info: dict, ip, app_info: dict, jti: str) -> list:
    """Retourne la liste des raisons pour lesquelles la connexion est inhabituelle."""
    raisons = []
    entreprise_id = claims.get("entrepriseId")
    entreprise_id = str(entreprise_id) if entreprise_id is not None else None

    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE adresse_ip = %s),
                       COUNT(*) FILTER (WHERE systeme = %s)
                FROM session_utilisateur
                WHERE type_compte = %s AND utilisateur_id = %s
                  AND entreprise_id IS NOT DISTINCT FROM %s AND jti <> %s
                """,
                (ip, info["systeme"], claims["type"], str(claims["id"]), entreprise_id, jti),
            )
            total, meme_ip, meme_systeme = cur.fetchone()
            cur.execute(
                "SELECT COUNT(*) FROM evenement_securite WHERE type_evenement = 'connexion_echouee' "
                "AND email = LOWER(%s) AND cree_le > NOW() - make_interval(mins => %s)",
                (claims["email"], FENETRE_ECHECS_MIN),
            )
            echecs = cur.fetchone()[0]
    finally:
        pool_central.putconn(conn)

    if app_info.get("nouveau"):
        raisons.append("nouvel_appareil")
    # Pas d'historique = premiere connexion du compte : rien d'inhabituel.
    if total > 0:
        if ip and meme_ip == 0:
            raisons.append("nouvelle_adresse_ip")
        if meme_systeme == 0:
            raisons.append("nouveau_systeme")
    if echecs >= SEUIL_ECHECS:
        raisons.append("apres_echecs_repetes")
    return raisons


def _notifier(type_compte, utilisateur_id, entreprise_id, titre, message, categorie="warning"):
    from app.routers.notifications import creer_notification  # import tardif : evite un cycle
    creer_notification(type_compte, str(utilisateur_id), entreprise_id, titre, message,
                       lien="/appareils", categorie=categorie)


def administrateurs(claims: dict) -> list:
    """Identifiants des administrateurs actifs de l'entreprise (hors l'utilisateur lui-meme)."""
    if claims.get("type") != "interne" or not claims.get("nomBase"):
        return []
    pool = get_pool_entreprise(claims["nomBase"])
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT u.id FROM utilisateur u JOIN role r ON r.id = u.role_id "
                "WHERE r.nom = 'Admin' AND u.actif = TRUE AND u.id <> %s",
                (claims["id"],),
            )
            return [str(l[0]) for l in cur.fetchall()]
    finally:
        pool.putconn(conn)


def _envoyer_email(destinataire: str, nom_appareil: str, ip, raisons: list) -> None:
    try:
        from app.utils.email_sender import envoyer_email
        motifs = "\n".join("  - " + LIBELLES.get(r, r) for r in raisons)
        corps = (
            "Bonjour,\n\n"
            "Une connexion inhabituelle à votre compte vient d'être détectée :\n"
            "  Appareil : {}\n  Adresse IP : {}\n  Date : {}\n\n"
            "Raison(s) :\n{}\n\n"
            "Si c'est bien vous, vous n'avez rien à faire. Sinon, ouvrez « Mes appareils », "
            "fermez ou bloquez cet appareil, puis changez votre mot de passe.\n\n— BENJEDDOU ERP"
        ).format(nom_appareil, ip or "inconnue", datetime.now().strftime("%d/%m/%Y %H:%M"), motifs)
        envoyer_email(destinataire, "Alerte de sécurité : connexion inhabituelle", corps)
    except Exception:
        _log.exception("Email d'alerte non envoye")


def traiter_connexion(claims: dict, request, info: dict, ip, app_info: dict, jti: str) -> list:
    """Evalue la connexion et declenche les alertes. Ne leve JAMAIS d'exception."""
    try:
        raisons = evaluer(claims, info, ip, app_info, jti)
        if not raisons:
            return []

        nom_appareil = "{} sur {}".format(info["navigateur"], info["systeme"])
        critique = "apres_echecs_repetes" in raisons and len(raisons) > 1
        journaliser(
            "connexion_inhabituelle", gravite="critique" if critique else "avertissement", succes=True,
            type_compte=claims["type"], utilisateur_id=claims["id"], email=claims["email"],
            entreprise_id=claims.get("entrepriseId"), jti=jti, request=request,
            details={"raison": ",".join(raisons)},
        )

        entreprise_id = claims.get("entrepriseId")
        entreprise_id = int(entreprise_id) if entreprise_id is not None else None
        motifs = ", ".join(LIBELLES.get(r, r) for r in raisons)
        try:
            _notifier(claims["type"], claims["id"], entreprise_id, "Connexion inhabituelle à votre compte",
                      "Connexion depuis {} (IP {}) : {}. Si ce n'est pas vous, fermez la session "
                      "dans « Mes appareils ».".format(nom_appareil, ip or "inconnue", motifs))
        except Exception:
            _log.exception("Notification utilisateur impossible")
        try:
            for admin_id in administrateurs(claims):
                _notifier("interne", admin_id, entreprise_id, "Connexion inhabituelle d'un collaborateur",
                          "{} s'est connecté depuis {} (IP {}) : {}.".format(
                              claims["email"], nom_appareil, ip or "inconnue", motifs))
        except Exception:
            _log.exception("Notification des administrateurs impossible")

        if os.getenv("ALERTES_EMAIL", "1") == "1":
            threading.Thread(target=_envoyer_email, args=(claims["email"], nom_appareil, ip, raisons),
                             daemon=True).start()
        return raisons
    except Exception:
        _log.exception("Analyse de la connexion impossible")
        return []


def notifier_appareil_en_attente(claims: dict, nom_appareil: str) -> None:
    """Mode strict : previent les administrateurs (et le compte lui-meme) qu'un
    nouvel appareil attend une autorisation. Ne leve jamais d'exception."""
    try:
        entreprise_id = claims.get("entrepriseId")
        entreprise_id = int(entreprise_id) if entreprise_id is not None else None
        message = "{} : l'appareil « {} » attend votre autorisation dans « Mes appareils ».".format(
            claims["email"], nom_appareil)
        destinataires = [(claims["type"], str(claims["id"]))]
        destinataires += [("interne", a) for a in administrateurs(claims)]
        for type_compte, uid in destinataires:
            try:
                _notifier(type_compte, uid, entreprise_id, "Nouvel appareil en attente d'autorisation", message)
            except Exception:
                _log.exception("Notification d'appareil en attente impossible")
    except Exception:
        _log.exception("Alerte d'appareil en attente impossible")
