import os
import re
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
from app.security import reset_password_store as reset_store
from app.utils.email_sender import envoyer_code_otp
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])

REGEX_LETTRE = re.compile(r"[A-Za-zÀ-ÿ]")
REGEX_CHIFFRE = re.compile(r"\d")
REGEX_SPECIAL = re.compile(r"[^A-Za-zÀ-ÿ0-9]")


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


def _chercher_super_admin(email: str):
    """Recherche dans la base centrale (Super Administrateur SaaS)."""
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nom, email, mot_de_passe FROM super_admin WHERE email = %s",
                (email,),
            )
            return cur.fetchone()
    finally:
        pool_central.putconn(conn)


def _chercher_entreprise_par_email_admin(email: str):
    """
    Étape 1 du routage multi-tenant : à partir d'un email, retrouve
    l'entreprise correspondante (et sa base dédiée) dans la base centrale.
    Ne présume pas que l'utilisateur y existe déjà — juste que l'entreprise
    est active et que sa base a été provisionnée.
    """
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nom_base, statut FROM entreprise WHERE email_contact = %s",
                (email,),
            )
            return cur.fetchone()
    finally:
        pool_central.putconn(conn)


def _chercher_utilisateur_entreprise(nom_base: str, email: str):
    """
    Étape 2 du routage multi-tenant : une fois la base de l'entreprise
    identifiée, on s'y connecte réellement pour vérifier les identifiants
    de l'utilisateur métier (ici l'administrateur créé au provisioning).
    """
    pool_tenant = get_pool_entreprise(nom_base)
    conn = pool_tenant.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.id, u.nom, u.prenom, u.email, u.mot_de_passe, u.actif, r.nom
                FROM utilisateur u
                LEFT JOIN role r ON r.id = u.role_id
                WHERE u.email = %s
                """,
                (email,),
            )
            return cur.fetchone()
    finally:
        pool_tenant.putconn(conn)


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

    # --- Couche 3a : d'abord, est-ce un Super Administrateur SaaS ? ---
    ligne_super_admin = _chercher_super_admin(email)

    if ligne_super_admin:
        utilisateur_id, nom, email_bd, hash_stocke = ligne_super_admin
        if bcrypt.checkpw(payload.motDePasse.encode("utf-8"), hash_stocke.encode("utf-8")):
            reinitialiser_tentatives(email)
            expiration = datetime.now(timezone.utc) + timedelta(hours=8)
            token = jwt.encode(
                {"id": utilisateur_id, "email": email_bd, "role": "super_admin", "exp": expiration},
                os.getenv("JWT_SECRET", "dev_secret_a_remplacer"),
                algorithm="HS256",
            )
            return {"token": token, "utilisateur": {"id": utilisateur_id, "nom": nom, "email": email_bd, "role": "super_admin"}}
        # Email de super admin trouvé mais mauvais mot de passe : on
        # traite l'échec normalement plus bas (pas de fuite d'information
        # sur l'existence du compte).

    # --- Couche 3b : sinon, routage multi-tenant vers la bonne entreprise ---
    ligne_entreprise = _chercher_entreprise_par_email_admin(email)
    utilisateur_tenant = None
    nom_base = None

    if ligne_entreprise:
        entreprise_id, nom_base, statut_entreprise = ligne_entreprise
        if statut_entreprise == "actif":
            utilisateur_tenant = _chercher_utilisateur_entreprise(nom_base, email)

    mot_de_passe_valide = False
    if utilisateur_tenant:
        utilisateur_id, nom, prenom, email_bd, hash_stocke, actif, role_nom = utilisateur_tenant
        mot_de_passe_valide = actif and bcrypt.checkpw(
            payload.motDePasse.encode("utf-8"), hash_stocke.encode("utf-8")
        )

    if not utilisateur_tenant or not mot_de_passe_valide:
        enregistrer_echec(email)
        etat_apres = etat_protection(email)

        # Cas particulier : l'entreprise existe mais n'est pas encore
        # activée (inscription en cours, pas encore payée/validée).
        if ligne_entreprise and ligne_entreprise[2] != "actif":
            return JSONResponse(status_code=403, content={
                "message": "Votre inscription n'est pas encore activée. Merci de terminer le parcours d'inscription.",
            })

        return JSONResponse(status_code=401, content={
            "message": "Adresse e-mail ou mot de passe incorrect.",
            "requiresCaptcha": etat_apres["protection_active"],
            "requiresRecaptcha": etat_apres["echecs"] >= 4,
        })

    reinitialiser_tentatives(email)

    expiration = datetime.now(timezone.utc) + timedelta(hours=8)
    token = jwt.encode(
        {
            "id": utilisateur_id, "email": email_bd, "role": role_nom or "utilisateur",
            "nomBase": nom_base, "exp": expiration,
        },
        os.getenv("JWT_SECRET", "dev_secret_a_remplacer"),
        algorithm="HS256",
    )

    return {
        "token": token,
        "utilisateur": {
            "id": utilisateur_id, "nom": f"{prenom} {nom}".strip(),
            "email": email_bd, "role": role_nom or "utilisateur",
        },
    }


# ===========================================================================
# Mot de passe oublié : demande de code -> vérification -> nouveau mot de
# passe, avec les mêmes règles de sécurité que l'inscription (politique de
# mot de passe, indicateur de force côté frontend, captcha).
# ===========================================================================

class DemandeReinitialisationPayload(BaseModel):
    email: str


class VerifierCodeReinitialisationPayload(BaseModel):
    email: str
    code: str


class ReinitialiserMotDePassePayload(BaseModel):
    email: str
    nouveauMotDePasse: str
    nouveauMotDePasseConfirmation: str
    captchaId: str
    captchaValeur: str


def _localiser_compte(email: str):
    """Retourne ('super_admin', None) ou ('tenant', nom_base) selon où
    vit ce compte, ou None si l'email n'existe nulle part. Réutilise la
    même logique de routage que /login."""
    if _chercher_super_admin(email):
        return ("super_admin", None)

    ligne_entreprise = _chercher_entreprise_par_email_admin(email)
    if ligne_entreprise:
        _, nom_base, statut = ligne_entreprise
        if statut == "actif" and _chercher_utilisateur_entreprise(nom_base, email):
            return ("tenant", nom_base)

    return None


@router.post("/mot-de-passe-oublie")
def demander_reinitialisation(payload: DemandeReinitialisationPayload):
    email = payload.email.strip().lower()

    # Toujours répondre le même message, que l'email existe ou non : ne
    # jamais révéler si une adresse est enregistrée dans le système
    # (principe standard de sécurité contre l'énumération de comptes).
    reponse_generique = {
        "message": "Si un compte existe avec cet email, un code de vérification vient d'être envoyé.",
    }

    localisation = _localiser_compte(email)
    if not localisation:
        return reponse_generique

    if not reset_store.peut_renvoyer(email):
        return reponse_generique

    code = reset_store.generer_et_stocker_otp(email)
    try:
        envoyer_code_otp(email, code)
    except Exception:
        pass  # on ne révèle jamais d'échec technique à l'appelant ici

    return reponse_generique


@router.post("/verifier-code-reinitialisation")
def verifier_code_reinitialisation(payload: VerifierCodeReinitialisationPayload):
    email = payload.email.strip().lower()
    ok, raison = reset_store.verifier_otp(email, payload.code)

    if not ok:
        messages = {
            "aucun_code_actif": "Aucune demande de réinitialisation active. Recommencez.",
            "trop_de_tentatives": "Trop de tentatives incorrectes. Demandez un nouveau code.",
            "expire": "Ce code a expiré. Demandez un nouveau code.",
            "code_incorrect": "Code incorrect.",
        }
        return JSONResponse(status_code=400, content={"message": messages.get(raison, "Code invalide.")})

    return {"message": "Code vérifié. Vous pouvez définir un nouveau mot de passe."}


@router.post("/reinitialiser-mot-de-passe")
def reinitialiser_mot_de_passe(payload: ReinitialiserMotDePassePayload):
    email = payload.email.strip().lower()

    if not reset_store.code_deja_verifie(email):
        return JSONResponse(status_code=400, content={
            "message": "Vérification du code requise avant de définir un nouveau mot de passe.",
        })

    if not verifier_et_consommer_captcha(payload.captchaId, payload.captchaValeur):
        return JSONResponse(status_code=400, content={"message": "Code de sécurité incorrect ou expiré."})

    mdp = payload.nouveauMotDePasse
    if (
        len(mdp) < 8
        or not REGEX_LETTRE.search(mdp)
        or not REGEX_CHIFFRE.search(mdp)
        or not REGEX_SPECIAL.search(mdp)
    ):
        return JSONResponse(status_code=400, content={
            "message": "Le mot de passe doit contenir au moins 8 caractères, avec des lettres, des chiffres et un caractère spécial.",
        })
    if mdp != payload.nouveauMotDePasseConfirmation:
        return JSONResponse(status_code=400, content={"message": "Les deux mots de passe ne correspondent pas."})

    localisation = _localiser_compte(email)
    if not localisation:
        # Ne devrait normalement pas arriver si le code a bien été vérifié
        # pour cet email, mais on reste défensif.
        return JSONResponse(status_code=404, content={"message": "Compte introuvable."})

    type_compte, nom_base = localisation
    nouveau_hash = bcrypt.hashpw(mdp.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    if type_compte == "super_admin":
        conn = pool_central.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE super_admin SET mot_de_passe = %s WHERE email = %s", (nouveau_hash, email))
            conn.commit()
        finally:
            pool_central.putconn(conn)
    else:
        pool_tenant = get_pool_entreprise(nom_base)
        conn = pool_tenant.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE utilisateur SET mot_de_passe = %s WHERE email = %s", (nouveau_hash, email))
            conn.commit()
        finally:
            pool_tenant.putconn(conn)

    reset_store.supprimer(email)
    reinitialiser_tentatives(email)  # efface aussi tout blocage captcha lié aux échecs de login précédents

    return {"message": "Mot de passe réinitialisé avec succès."}
