"""Essai gratuit : compteur de connexions cote serveur (atomique en SQL)."""
import logging
import os
import threading

from fastapi.responses import JSONResponse

from app.db import get_pool_entreprise, pool_central
from app.security.audit import journaliser

_log = logging.getLogger("essai")
MARGE_ALERTE = 5  # alerte quand il reste 5 connexions, puis a la derniere


def _consommer(entreprise_id):
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT essai, autorise, utilisees, maximum FROM consommer_connexion_essai(%s)",
                (entreprise_id,),
            )
            ligne = cur.fetchone()
        conn.commit()  # libere le verrou de ligne et conserve le compteur
        return ligne
    except Exception:
        conn.rollback()
        raise
    finally:
        pool_central.putconn(conn)


def lire_statut_essai(entreprise_id):
    """Lecture seule : None si l'entreprise n'est pas en essai."""
    if entreprise_id is None:
        return None
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT connexions_essai_max, connexions_essai_utilisees FROM abonnement "
                "WHERE entreprise_id = %s ORDER BY id DESC LIMIT 1",
                (entreprise_id,),
            )
            ligne = cur.fetchone()
    finally:
        pool_central.putconn(conn)
    if not ligne or ligne[0] is None:
        return None
    maximum, utilisees = ligne
    return {"utilisees": utilisees, "maximum": maximum, "restantes": max(0, maximum - utilisees)}


def _admins(nom_base):
    pool = get_pool_entreprise(nom_base)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT u.id FROM utilisateur u JOIN role r ON r.id = u.role_id "
                "WHERE r.nom = 'Admin' AND u.actif = TRUE"
            )
            return [str(l[0]) for l in cur.fetchall()]
    finally:
        pool.putconn(conn)


def _email_contact(entreprise_id):
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT email_contact FROM entreprise WHERE id = %s", (entreprise_id,))
            ligne = cur.fetchone()
    finally:
        pool_central.putconn(conn)
    return ligne[0] if ligne else None


def _notifier_seuil(entreprise_id, nom_base, utilisees, maximum):
    """Notification dans l'application (administrateurs) + email au contact. Ne leve jamais."""
    try:
        from app.routers.notifications import creer_notification  # import tardif : evite un cycle
        restantes = maximum - utilisees
        if restantes > 0:
            titre = "Essai gratuit : {} connexion(s) restante(s)".format(restantes)
            message = ("Votre essai gratuit a utilis\u00e9 {} connexions sur {}. Pensez \u00e0 "
                       "souscrire un abonnement pour continuer.").format(utilisees, maximum)
            categorie = "warning"
        else:
            titre = "Essai gratuit : derni\u00e8re connexion utilis\u00e9e"
            message = ("Les {} connexions de l'essai sont utilis\u00e9es : la prochaine connexion sera "
                       "refus\u00e9e. Souscrivez un abonnement pour continuer.").format(maximum)
            categorie = "error"
        for admin_id in _admins(nom_base):
            try:
                creer_notification("interne", admin_id, int(entreprise_id), titre, message,
                                   lien="/", categorie=categorie)
            except Exception:
                _log.exception("Notification d'essai impossible")
        email = _email_contact(entreprise_id)
        if email and os.getenv("ALERTES_EMAIL", "1") == "1":
            from app.utils.email_sender import envoyer_email
            envoyer_email(email, titre, message + "\n\n\u2014 BENJEDDOU ERP")
    except Exception:
        _log.exception("Alerte de fin d'essai impossible")


def controler_essai(entreprise_id, nom_base, type_compte, email, request):
    """Appele APRES la verification du mot de passe, AVANT emettre_jeton.
    Retourne (reponse_403 | None, infos_essai | None)."""
    essai, autorise, utilisees, maximum = _consommer(entreprise_id)
    if not essai:
        return None, None

    if not autorise:
        journaliser("connexion_refusee", gravite="avertissement", succes=False,
                    type_compte=type_compte, email=email, entreprise_id=entreprise_id,
                    request=request, details={"raison": "essai_epuise"})
        return JSONResponse(status_code=403, content={
            "message": ("La p\u00e9riode d'essai ({} connexions) est termin\u00e9e. "
                        "Souscrivez un abonnement pour continuer.").format(maximum),
            "essaiEpuise": True,
        }), None

    if utilisees in (maximum - MARGE_ALERTE, maximum):
        threading.Thread(target=_notifier_seuil,
                         args=(entreprise_id, nom_base, utilisees, maximum), daemon=True).start()
    return None, {"utilisees": utilisees, "maximum": maximum, "restantes": maximum - utilisees}