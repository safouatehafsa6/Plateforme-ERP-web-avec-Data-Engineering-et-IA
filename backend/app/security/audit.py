"""Journal des evenements de securite (table evenement_securite).

journaliser() ne leve JAMAIS d'exception : le journal ne doit pas casser
une connexion. Seules les cles de _CLES_DETAILS sont conservees (jamais de
mot de passe, de jeton ou de secret).
"""
import ipaddress
import json
import logging

from app.db import pool_central

_log = logging.getLogger("audit")

_CLES_DETAILS = {"motif", "raison", "nb", "cible_email", "cible_jti", "cible_type", "cible_id"}


def _txt(valeur, taille):
    return None if valeur is None else str(valeur)[:taille]


def _nettoyer(details):
    if not details:
        return {}
    propre = {}
    for cle, valeur in details.items():
        if cle in _CLES_DETAILS:
            propre[cle] = valeur if isinstance(valeur, (int, float, bool)) else str(valeur)[:200]
    return propre


def journaliser(
    type_evenement,
    *,
    gravite="info",
    succes=None,
    type_compte=None,
    utilisateur_id=None,
    email=None,
    entreprise_id=None,
    jti=None,
    request=None,
    acteur_email=None,
    details=None,
):
    try:
        ip = systeme = navigateur = None
        if request is not None:
            from app.security.sessions import adresse_ip, analyser_user_agent
            ip = adresse_ip(request)
            info = analyser_user_agent(request.headers.get("user-agent", ""))
            systeme, navigateur = info["systeme"], info["navigateur"]
        if ip:
            try:
                ip = str(ipaddress.ip_address(ip))
            except ValueError:
                ip = None

        conn = pool_central.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO evenement_securite
                        (type_evenement, gravite, succes, type_compte, utilisateur_id, email,
                         entreprise_id, jti, adresse_ip, systeme, navigateur, acteur_email, details)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::inet, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        _txt(type_evenement, 40), gravite, succes, _txt(type_compte, 12),
                        _txt(utilisateur_id, 64),
                        _txt(email.strip().lower(), 255) if email else None,
                        _txt(entreprise_id, 64), _txt(jti, 64), ip,
                        _txt(systeme, 60), _txt(navigateur, 60),
                        _txt(acteur_email.strip().lower(), 255) if acteur_email else None,
                        json.dumps(_nettoyer(details)),
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            pool_central.putconn(conn)
    except Exception:
        _log.exception("Journalisation de securite impossible (%s)", type_evenement)