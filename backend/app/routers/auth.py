import os
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter
from pydantic import BaseModel

from app.db import pool_central
from app.security.captcha import generer_captcha
from app.security.protection import (
    enregistrer_captcha,
    verifier_et_consommer_captcha,
    etat_protection,
    enregistrer_echec,
    reinitialiser_tentatives,
)
from app.security.recaptcha import verifier_recaptcha
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
    # NOTE : démo de sécurité sur la table super_admin de la base centrale.
    # Le routage complet vers les bases entreprise (utilisateur métier) est
    # en cours d'implémentation en parallèle (diagramme de séquence
    # "Routage multi-tenant").
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nom, email, mot_de_passe FROM super_admin WHERE email = %s",
                (email,),
            )
            ligne = cur.fetchone()
    finally:
        pool_central.putconn(conn)

    mot_de_passe_valide = False
    if ligne:
        utilisateur_id, nom, email_bd, hash_stocke = ligne
        mot_de_passe_valide = bcrypt.checkpw(
            payload.motDePasse.encode("utf-8"), hash_stocke.encode("utf-8")
        )

    if not ligne or not mot_de_passe_valide:
        enregistrer_echec(email)
        etat_apres = etat_protection(email)
        return JSONResponse(status_code=401, content={
            "message": "Adresse e-mail ou mot de passe incorrect.",
            "requiresCaptcha": etat_apres["protection_active"],
            "requiresRecaptcha": etat_apres["echecs"] >= 4,
        })

    # Connexion réussie : on efface le compteur d'échecs pour cet email.
    reinitialiser_tentatives(email)

    expiration = datetime.now(timezone.utc) + timedelta(hours=8)
    token = jwt.encode(
        {"id": utilisateur_id, "email": email_bd, "role": "super_admin", "exp": expiration},
        os.getenv("JWT_SECRET", "dev_secret_a_remplacer"),
        algorithm="HS256",
    )

    return {"token": token, "utilisateur": {"id": utilisateur_id, "nom": nom, "email": email_bd}}
