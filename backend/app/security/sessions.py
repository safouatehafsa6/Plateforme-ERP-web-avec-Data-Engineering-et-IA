"""Sessions actives : emission du JWT avec jti, verification a chaque
requete, revocation.

Toutes les sessions sont stockees dans la base centrale
(table session_utilisateur, voir 006_sessions_utilisateur.sql), pour les
trois profils : plateforme (super admin), interne et externe.
"""
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Request

from app.db import pool_central

DUREE_SESSION = timedelta(hours=8)
# On ne met a jour "derniere_activite" qu'une fois par minute au plus,
# pour ne pas ecrire en base a chaque requete.
INTERVALLE_ACTIVITE = timedelta(seconds=60)


def adresse_ip(request: Request) -> str | None:
    # Derriere un reverse proxy (nginx, Traefik...), l'IP reelle est dans
    # X-Forwarded-For. On ne lui fait confiance que si TRUST_PROXY=1,
    # sinon n'importe quel client pourrait falsifier son adresse.
    if os.getenv("TRUST_PROXY", "0") == "1":
        transfere = request.headers.get("x-forwarded-for")
        if transfere:
            return transfere.split(",")[0].strip()[:45]
    return request.client.host if request.client else None


def analyser_user_agent(ua: str | None) -> dict:
    ua = ua or ""

    if re.search(r"iPhone|iPad|iPod", ua):
        systeme = "iOS"
    elif "Android" in ua:
        systeme = "Android"
    elif "Windows" in ua:
        systeme = "Windows"
    elif "Mac OS X" in ua or "Macintosh" in ua:
        systeme = "macOS"
    elif "CrOS" in ua:
        systeme = "ChromeOS"
    elif "Linux" in ua:
        systeme = "Linux"
    else:
        systeme = "Système inconnu"

    # L'ordre compte : Edge et Opera contiennent aussi "Chrome" et "Safari".
    if "Edg/" in ua or "EdgA/" in ua or "EdgiOS/" in ua:
        navigateur = "Edge"
    elif "OPR/" in ua or "Opera" in ua:
        navigateur = "Opera"
    elif "Firefox/" in ua or "FxiOS/" in ua:
        navigateur = "Firefox"
    elif "Chrome/" in ua or "CriOS/" in ua:
        navigateur = "Chrome"
    elif "Safari/" in ua:
        navigateur = "Safari"
    else:
        navigateur = "Navigateur inconnu"

    appareil = "mobile" if re.search(r"Mobi|iPhone|iPad|Android", ua) else "ordinateur"
    return {"systeme": systeme, "navigateur": navigateur, "appareil": appareil}


def emettre_jeton(claims: dict, request: Request) -> str:
    """Cree la session en base puis signe le JWT contenant son jti.

    `claims` = les champs habituels du jeton (id, email, role, type,
    nomBase, entrepriseId, clientId...), SANS exp ni jti.
    """
    jti = uuid.uuid4().hex
    expiration = datetime.now(timezone.utc) + DUREE_SESSION
    ua = request.headers.get("user-agent", "")
    info = analyser_user_agent(ua)
    entreprise_id = claims.get("entrepriseId")

    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            # Nettoyage opportuniste : historique conserve 30 jours.
            cur.execute(
                "DELETE FROM session_utilisateur WHERE expire_le < NOW() - INTERVAL '30 days'"
            )
            cur.execute(
                """
                INSERT INTO session_utilisateur
                    (jti, type_compte, utilisateur_id, email, entreprise_id, nom_base,
                     systeme, navigateur, appareil, adresse_ip, user_agent, expire_le)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    jti, claims["type"], str(claims["id"]), claims["email"],
                    str(entreprise_id) if entreprise_id is not None else None,
                    claims.get("nomBase"),
                    info["systeme"], info["navigateur"], info["appareil"],
                    adresse_ip(request), ua[:500], expiration,
                ),
            )
        conn.commit()
    finally:
        pool_central.putconn(conn)

    return jwt.encode(
        {**claims, "jti": jti, "exp": expiration},
        os.environ["JWT_SECRET"],
        algorithm="HS256",
    )


def verifier_session(charge: dict) -> None:
    """A appeler apres le decodage du JWT : leve 401 si la session est
    inconnue, revoquee ou expiree. Un jeton sans jti (emis avant cette
    fonctionnalite) est refuse : la personne doit se reconnecter."""
    jti = charge.get("jti")
    if not jti:
        raise HTTPException(status_code=401, detail="Session invalide, merci de vous reconnecter.")

    maintenant = datetime.now(timezone.utc)
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT revoquee_le, expire_le, derniere_activite FROM session_utilisateur WHERE jti = %s",
                (jti,),
            )
            ligne = cur.fetchone()

            if not ligne or ligne[0] is not None or ligne[1] <= maintenant:
                raise HTTPException(
                    status_code=401,
                    detail="Cette session a été fermée ou a expiré. Merci de vous reconnecter.",
                )

            if maintenant - ligne[2] > INTERVALLE_ACTIVITE:
                cur.execute(
                    "UPDATE session_utilisateur SET derniere_activite = NOW() WHERE jti = %s",
                    (jti,),
                )
                conn.commit()
    finally:
        pool_central.putconn(conn)


def revoquer_sessions_par_email(email: str, motif: str, type_compte: str | None = None) -> int:
    """Ferme toutes les sessions actives d'une adresse email (ex. apres
    une reinitialisation de mot de passe)."""
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            requete = """
                UPDATE session_utilisateur
                SET revoquee_le = NOW(), motif_revocation = %s
                WHERE LOWER(email) = LOWER(%s) AND revoquee_le IS NULL
            """
            params = [motif, email]
            if type_compte:
                requete += " AND type_compte = %s"
                params.append(type_compte)
            cur.execute(requete, params)
            nombre = cur.rowcount
        conn.commit()
        return nombre
    finally:
        pool_central.putconn(conn)
