import os
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter
from pydantic import BaseModel

from app.db import pool_central, get_pool_entreprise
from app.security.captcha import generer_captcha
from app.security.protection import (
    enregistrer_captcha,
    verifier_et_consommer_captcha,
    etat_protection,
    enregistrer_echec,
    reinitialiser_tentatives,
)
from app.security.recaptcha import verifier_recaptcha
from app.security.validation_inscription import valider_mot_de_passe
from app.security import password_reset_store as reset_store
from app.utils.email_sender import envoyer_code_reinitialisation
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginPayload(BaseModel):
    email: str
    motDePasse: str
    captchaId: str | None = None
    captchaValeur: str | None = None
    recaptchaToken: str | None = None


@router.get("/captcha")
def obtenir_captcha():
    captcha = generer_captcha()
    enregistrer_captcha(captcha["id"], captcha["code"])
    if os.getenv("ENV", "dev") != "production":
        print(f"[DEV] Captcha {captcha['id']} -> code: {captcha['code']}")
    return {"captchaId": captcha["id"], "svg": captcha["svg"]}


@router.post("/login")
async def login(payload: LoginPayload):
    email = payload.email.strip().lower()
    etat = etat_protection(email)

    # --- Couche 1 : après 2 échecs, le captcha local devient obligatoire ---
    if etat["protection_active"]:
        if not payload.captchaId or not payload.captchaValeur:
            return JSONResponse(status_code=400, content={
                "message": "Vérification de sécurité requise.",
                "requiresCaptcha": True,
                "requiresRecaptcha": etat["echecs"] >= 4,
            })

        if not verifier_et_consommer_captcha(payload.captchaId, payload.captchaValeur):
            enregistrer_echec(email)
            return JSONResponse(status_code=400, content={
                "message": "Code de sécurité incorrect ou expiré.",
                "requiresCaptcha": True,
                "requiresRecaptcha": etat["echecs"] >= 4,
            })

        # --- Couche 2 : après 4 échecs, reCAPTCHA obligatoire en plus ---
        if etat["echecs"] >= 4:
            if not await verifier_recaptcha(payload.recaptchaToken):
                enregistrer_echec(email)
                return JSONResponse(status_code=400, content={
                    "message": "Vérification reCAPTCHA échouée.",
                    "requiresCaptcha": True,
                    "requiresRecaptcha": True,
                })

    # --- Couche 3 : vérification réelle des identifiants ---
    # Point d'entrée unique pour tous les profils (Super Administrateur
    # ET comptes d'entreprise) : on cherche d'abord dans la base centrale
    # (super_admin), puis, si l'email n'y figure pas, dans l'index central
    # des comptes d'entreprise (compte_index) pour savoir dans quelle base
    # entreprise chercher — sans que la personne ait à préciser elle-même
    # à quelle entreprise elle appartient (voir diagramme de séquence
    # "Routage multi-tenant").
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nom, email, mot_de_passe FROM super_admin WHERE email = %s",
                (email,),
            )
            ligne_super_admin = cur.fetchone()

            ligne_index = None
            if not ligne_super_admin:
                cur.execute(
                    "SELECT entreprise_id, nom_base FROM compte_index WHERE email = %s",
                    (email,),
                )
                ligne_index = cur.fetchone()
    finally:
        pool_central.putconn(conn)

    if ligne_super_admin:
        utilisateur_id, nom, email_bd, hash_stocke = ligne_super_admin
        mot_de_passe_valide = bcrypt.checkpw(payload.motDePasse.encode("utf-8"), hash_stocke.encode("utf-8"))

        if not mot_de_passe_valide:
            enregistrer_echec(email)
            etat_apres = etat_protection(email)
            return JSONResponse(status_code=401, content={
                "message": "Adresse e-mail ou mot de passe incorrect.",
                "requiresCaptcha": etat_apres["protection_active"],
                "requiresRecaptcha": etat_apres["echecs"] >= 4,
            })

        reinitialiser_tentatives(email)
        expiration = datetime.now(timezone.utc) + timedelta(hours=8)
        token = jwt.encode(
            {"id": utilisateur_id, "email": email_bd, "role": "super_admin", "exp": expiration},
            os.getenv("JWT_SECRET", "dev_secret_a_remplacer"),
            algorithm="HS256",
        )
        return {"token": token, "utilisateur": {"id": utilisateur_id, "nom": nom, "email": email_bd}}

    if ligne_index:
        entreprise_id, nom_base = ligne_index

        # L'abonnement doit être actif pour autoriser la connexion —
        # sinon, on bloque avant même d'atteindre la base de l'entreprise
        # (une entreprise suspendue/en_attente/refusée n'a pas accès).
        conn = pool_central.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT statut FROM entreprise WHERE id = %s", (entreprise_id,))
                ligne_statut = cur.fetchone()
        finally:
            pool_central.putconn(conn)

        if not ligne_statut or ligne_statut[0] != "actif":
            return JSONResponse(status_code=403, content={
                "message": "Ce compte entreprise n'est pas (ou plus) actif. Contactez votre administrateur.",
            })

        pool_tenant = get_pool_entreprise(nom_base)
        conn = pool_tenant.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT u.id, u.nom, u.prenom, u.mot_de_passe, u.actif, r.nom AS role_nom
                    FROM utilisateur u
                    LEFT JOIN role r ON r.id = u.role_id
                    WHERE u.email = %s
                    """,
                    (email,),
                )
                ligne_utilisateur = cur.fetchone()
        finally:
            pool_tenant.putconn(conn)

        if ligne_utilisateur:
            utilisateur_id, nom, prenom, hash_stocke, actif, role_nom = ligne_utilisateur
            mot_de_passe_valide = actif and bcrypt.checkpw(payload.motDePasse.encode("utf-8"), hash_stocke.encode("utf-8"))

            if mot_de_passe_valide:
                reinitialiser_tentatives(email)
                expiration = datetime.now(timezone.utc) + timedelta(hours=8)
                token = jwt.encode(
                    {
                        "id": utilisateur_id, "email": email, "role": role_nom or "Utilisateur",
                        "nomBase": nom_base, "entrepriseId": entreprise_id, "exp": expiration,
                    },
                    os.getenv("JWT_SECRET", "dev_secret_a_remplacer"),
                    algorithm="HS256",
                )
                return {
                    "token": token,
                    "utilisateur": {
                        "id": utilisateur_id, "nom": f"{prenom} {nom}".strip(), "email": email,
                        "role": role_nom, "entrepriseId": entreprise_id,
                    },
                }

    # Ni super_admin, ni compte d'entreprise valide : même message
    # générique dans tous les cas (anti-énumération).
    enregistrer_echec(email)
    etat_apres = etat_protection(email)
    return JSONResponse(status_code=401, content={
        "message": "Adresse e-mail ou mot de passe incorrect.",
        "requiresCaptcha": etat_apres["protection_active"],
        "requiresRecaptcha": etat_apres["echecs"] >= 4,
    })



# ---------------------------------------------------------------------
# Parcours "Mot de passe oublié" : email -> code OTP -> nouveau mot de
# passe (mêmes règles de sécurité que l'inscription : politique de mot
# de passe, indicateur de force côté frontend, CAPTCHA côté backend).
# Toutes les validations sont revérifiées ici, jamais uniquement côté
# frontend — même principe que pour l'inscription (voir entreprises.py).
#
# Sécurité : la vérification du code OTP émet un jeton de réinitialisation
# à usage unique et imprévisible (password_reset_store.py), exigé pour
# l'étape finale. Sans ce jeton, connaître uniquement l'email ne suffit
# pas à déclencher le changement de mot de passe — contrairement à une
# implémentation qui se contenterait de marquer l'email comme "autorisé"
# pendant N minutes, ce qui laisserait une fenêtre où un tiers connaissant
# l'email (mais pas le code reçu par la victime) pourrait changer le mot
# de passe à sa place.
# ---------------------------------------------------------------------

MESSAGE_GENERIQUE_ENVOI_OTP = (
    "Si un compte existe avec cette adresse email, un code de "
    "vérification vient de lui être envoyé."
)


def _compte_existe(email: str) -> bool:
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM super_admin WHERE email = %s", (email,))
            return cur.fetchone() is not None
    finally:
        pool_central.putconn(conn)


class DemandeResetPayload(BaseModel):
    email: str


@router.post("/mot-de-passe-oublie")
def demander_reinitialisation(payload: DemandeResetPayload):
    email = payload.email.strip().lower()

    # On ne renvoie jamais une erreur différente selon que le compte
    # existe ou non : la réponse HTTP est identique dans les deux cas
    # (anti-énumération des comptes).
    if _compte_existe(email) and reset_store.peut_renvoyer_otp(email):
        code = reset_store.generer_et_stocker_otp(email)
        try:
            envoyer_code_reinitialisation(email, code)
        except Exception:
            print(f"[ERREUR] Échec d'envoi de l'email de réinitialisation à {email}")

    return {"message": MESSAGE_GENERIQUE_ENVOI_OTP}


class RenvoiResetOtpPayload(BaseModel):
    email: str


@router.post("/renvoyer-code-reinitialisation")
def renvoyer_code_reinitialisation(payload: RenvoiResetOtpPayload):
    email = payload.email.strip().lower()

    if not reset_store.peut_renvoyer_otp(email):
        attente = reset_store.secondes_avant_renvoi(email)
        return JSONResponse(status_code=429, content={
            "message": f"Veuillez patienter {attente} secondes avant de redemander un code.",
            "secondesAvantRenvoi": attente,
        })

    if _compte_existe(email):
        code = reset_store.generer_et_stocker_otp(email)
        try:
            envoyer_code_reinitialisation(email, code)
        except Exception:
            print(f"[ERREUR] Échec d'envoi de l'email de réinitialisation à {email}")

    return {"message": MESSAGE_GENERIQUE_ENVOI_OTP}


class VerifierResetOtpPayload(BaseModel):
    email: str
    code: str


@router.post("/verifier-code-reinitialisation")
def verifier_code_reinitialisation(payload: VerifierResetOtpPayload):
    email = payload.email.strip().lower()
    succes, raison = reset_store.verifier_otp(email, payload.code)

    if not succes:
        messages = {
            "aucun_code_actif": "Aucun code actif. Demandez un nouveau code.",
            "trop_de_tentatives": "Trop de tentatives incorrectes. Demandez un nouveau code.",
            "expire": "Ce code a expiré. Demandez un nouveau code.",
            "code_incorrect": "Code incorrect.",
        }
        return JSONResponse(status_code=400, content={"message": messages.get(raison, "Code invalide."), "raison": raison})

    # Jeton à usage unique, exigé pour l'étape suivante : empêche un
    # appel direct à /reinitialiser-mot-de-passe sans passer par la
    # vérification du code.
    return {"message": "Vérification réussie.", "jetonReset": reset_store.obtenir_jeton_reset(email)}


class ReinitialiserMotDePassePayload(BaseModel):
    email: str
    jetonReset: str
    nouveauMotDePasse: str
    nouveauMotDePasseConfirmation: str
    captchaId: str
    captchaValeur: str


@router.get("/captcha-reinitialisation")
def obtenir_captcha_reinitialisation():
    """Captcha dédié à l'étape finale de réinitialisation (même exigence
    que pour l'inscription : le nouveau mot de passe doit être protégé
    par un CAPTCHA, en plus du jeton de réinitialisation)."""
    captcha = generer_captcha()
    enregistrer_captcha(captcha["id"], captcha["code"])
    return {"captchaId": captcha["id"], "svg": captcha["svg"]}


@router.post("/reinitialiser-mot-de-passe")
def reinitialiser_mot_de_passe(payload: ReinitialiserMotDePassePayload):
    email = payload.email.strip().lower()

    if not reset_store.verifier_et_consommer_jeton_reset(email, payload.jetonReset):
        return JSONResponse(status_code=400, content={
            "message": "Session de réinitialisation invalide ou expirée. Recommencez la procédure.",
        })

    if not verifier_et_consommer_captcha(payload.captchaId, payload.captchaValeur):
        return JSONResponse(status_code=400, content={"message": "Code de sécurité incorrect ou expiré."})

    # Même politique de mot de passe que pour l'inscription (8 caractères
    # minimum, lettres + chiffres + caractère spécial), revérifiée ici.
    erreur = valider_mot_de_passe(payload.nouveauMotDePasse, payload.nouveauMotDePasseConfirmation)
    if erreur:
        return JSONResponse(status_code=400, content={"message": erreur})

    if not _compte_existe(email):
        return JSONResponse(status_code=400, content={
            "message": "Session de réinitialisation invalide ou expirée. Recommencez la procédure.",
        })

    nouveau_hash = bcrypt.hashpw(payload.nouveauMotDePasse.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE super_admin SET mot_de_passe = %s WHERE email = %s", (nouveau_hash, email))
        conn.commit()
    finally:
        pool_central.putconn(conn)

    # Par sécurité, on efface aussi les échecs de connexion enregistrés
    # pour cet email : un nouveau mot de passe légitime ne doit pas
    # rester bloqué derrière l'ancien compteur d'échecs.
    reinitialiser_tentatives(email)

    return {"message": "Mot de passe mis à jour avec succès. Vous pouvez vous connecter."}
