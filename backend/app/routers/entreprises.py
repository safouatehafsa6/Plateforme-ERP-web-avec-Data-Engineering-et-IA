import logging
import os
import re
import secrets
import unicodedata
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel

from app.db import pool_central
from app.security.jwt_utils import exiger_super_admin, obtenir_utilisateur_courant
from app.security.captcha import generer_captcha
from app.security.protection import enregistrer_captcha, verifier_et_consommer_captcha
from app.security.onboarding_store import (
    generer_et_stocker_otp,
    verifier_otp,
    peut_renvoyer_otp,
    secondes_avant_renvoi,
    stocker_admin_temporaire,
    recuperer_admin_temporaire,
    supprimer_admin_temporaire,
    email_verifie,
)
from app.services.provisioning import provisionner_entreprise
from app.utils.email_sender import envoyer_code_otp

router = APIRouter(prefix="/api/entreprises", tags=["entreprises"])

CGU_VERSION_ACTUELLE = "v1"

_bearer_optionnel = HTTPBearer(auto_error=False)


def _auto_validation_active() -> bool:
    """Mode demonstration / developpement UNIQUEMENT : validation automatique
    du dossier et activation sans Super Admin. Desactive par defaut ; a ne
    jamais activer en production (ONBOARDING_AUTO_VALIDATION=1)."""
    return os.getenv("ONBOARDING_AUTO_VALIDATION", "0") == "1"


DUREE_JETON_INSCRIPTION = timedelta(hours=2)
PLANS_VALIDES = ("essai", "standard", "premium")


def _super_admin_optionnel(identifiants=Depends(_bearer_optionnel)):
    """Super Admin authentifie si un jeton de session est fourni, sinon None.
    Un jeton de session invalide est refuse (401)."""
    if identifiants is None:
        return None
    utilisateur = obtenir_utilisateur_courant(identifiants)
    return exiger_super_admin(utilisateur)


def _emettre_jeton_inscription(entreprise_id) -> str:
    """Jeton signe, a duree limitee, delivre APRES validation de l'OTP.
    Il porte une audience speciale : il est refuse partout ailleurs (jamais
    accepte comme jeton de session)."""
    return jwt.encode(
        {
            "sub": str(entreprise_id),
            "scope": "inscription",
            "aud": "inscription",
            "exp": datetime.now(timezone.utc) + DUREE_JETON_INSCRIPTION,
        },
        os.environ["JWT_SECRET"],
        algorithm="HS256",
    )


def _exiger_jeton_inscription(entreprise_id, jeton) -> None:
    """401 si le jeton est absent/invalide/expire, 403 s'il concerne une
    autre entreprise."""
    if not jeton:
        raise HTTPException(status_code=401, detail="Jeton d'inscription manquant. Recommencez la vérification de l'email.")
    try:
        charge = jwt.decode(jeton, os.environ["JWT_SECRET"], algorithms=["HS256"], audience="inscription")
    except (jwt.InvalidTokenError, KeyError):
        raise HTTPException(status_code=401, detail="Jeton d'inscription invalide ou expiré.")
    if charge.get("scope") != "inscription" or charge.get("sub") != str(entreprise_id):
        raise HTTPException(status_code=403, detail="Ce jeton ne correspond pas à cette inscription.")


def _plan_est_essai(entreprise_id) -> bool:
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT type_plan FROM abonnement WHERE entreprise_id = %s ORDER BY id DESC LIMIT 1",
                (entreprise_id,),
            )
            ligne = cur.fetchone()
    finally:
        pool_central.putconn(conn)
    return bool(ligne) and ligne[0] == "essai"

# Format email volontairement strict : présence d'un "@", d'un domaine
# avec au moins un point, et aucun espace (voir demande de l'entreprise,
# section 4 — validation email).
REGEX_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

# Politique de mot de passe (section 5) : 8 caractères minimum, au moins
# une lettre, un chiffre et un caractère spécial.
REGEX_LETTRE = re.compile(r"[A-Za-zÀ-ÿ]")
REGEX_CHIFFRE = re.compile(r"\d")
REGEX_SPECIAL = re.compile(r"[^A-Za-zÀ-ÿ0-9]")

# Documents KYC attendus selon le type de compte, conformément à la
# précision de l'entreprise sur le parcours KYC.
DOCUMENTS_REQUIS = {
    "personne_physique": ["cin"],
    "entreprise": ["cin_gerant", "patente", "extrait_rne"],
}


def _slugifier(texte: str) -> str:
    texte = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode("ascii")
    texte = re.sub(r"[^a-zA-Z0-9]+", "_", texte).strip("_").lower()
    return texte or "compte"


def _erreurs_validation_inscription(payload: "InscriptionPayload") -> list[str]:
    """
    Toutes les règles de validation métier, appliquées côté serveur —
    jamais uniquement côté frontend (principe explicitement demandé par
    l'entreprise, section 8 et 11 : 'ne jamais faire confiance uniquement
    aux données provenant du Frontend').
    """
    erreurs = []

    if payload.typeCompte not in DOCUMENTS_REQUIS:
        erreurs.append("Type de compte invalide.")
        return erreurs  # les vérifications suivantes dépendent du type

    if payload.typeCompte == "entreprise" and not (payload.nomEntreprise or "").strip():
        erreurs.append("Le nom de l'entreprise est obligatoire pour ce type de compte.")

    if not (payload.nomAdmin or "").strip():
        erreurs.append("Le nom complet est obligatoire.")

    email = (payload.email or "").strip()
    email_confirmation = (payload.emailConfirmation or "").strip()
    if " " in payload.email or " " in payload.emailConfirmation:
        erreurs.append("L'adresse email ne doit contenir aucun espace.")
    elif not REGEX_EMAIL.match(email):
        erreurs.append("Adresse email invalide.")
    elif email.lower() != email_confirmation.lower():
        erreurs.append("Les deux adresses email ne correspondent pas.")

    mdp = payload.motDePasse or ""
    if (
        len(mdp) < 8
        or not REGEX_LETTRE.search(mdp)
        or not REGEX_CHIFFRE.search(mdp)
        or not REGEX_SPECIAL.search(mdp)
    ):
        erreurs.append(
            "Le mot de passe doit contenir au moins 8 caractères, avec des "
            "lettres, des chiffres et un caractère spécial."
        )
    elif mdp != payload.motDePasseConfirmation:
        erreurs.append("Les deux mots de passe ne correspondent pas.")

    if not payload.cguAccepte:
        erreurs.append("Vous devez accepter les conditions d'utilisation pour continuer.")

    return erreurs


# --- Étape 1 : choix du type + inscription ---
class InscriptionPayload(BaseModel):
    typeCompte: str  # "personne_physique" | "entreprise"
    nomEntreprise: str | None = None   # requis si entreprise
    secteur: str | None = None
    nomAdmin: str                       # nom complet (personne physique) ou nom du représentant (entreprise)
    email: str
    emailConfirmation: str
    telephone: str | None = None
    motDePasse: str
    motDePasseConfirmation: str
    cguAccepte: bool
    captchaId: str
    captchaValeur: str


@router.get("/captcha")
def obtenir_captcha_inscription():
    """Captcha dédié au formulaire d'inscription (section 6 : protection
    anti-robot — une case à cocher seule n'est pas jugée suffisante)."""
    captcha = generer_captcha()
    enregistrer_captcha(captcha["id"], captcha["code"])
    return {"captchaId": captcha["id"], "svg": captcha["svg"]}


@router.post("/inscription")
def inscription(payload: InscriptionPayload):
    erreurs = _erreurs_validation_inscription(payload)
    if erreurs:
        return JSONResponse(status_code=400, content={
            "message": erreurs[0],
            "erreurs": erreurs,
        })

    if not verifier_et_consommer_captcha(payload.captchaId, payload.captchaValeur):
        return JSONResponse(status_code=400, content={
            "message": "Code de sécurité incorrect ou expiré.",
        })

    email = payload.email.strip().lower()

    # Anti-doublon (section 10) : un email ne peut être utilisé que pour
    # une seule inscription.
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM entreprise WHERE email_contact = %s "
                "UNION SELECT 1 FROM compte_index WHERE email = %s",
                (email, email),
            )
            if cur.fetchone():
                return JSONResponse(status_code=409, content={
                    "message": "Une inscription existe déjà avec cette adresse email.",
                })
    finally:
        pool_central.putconn(conn)

    identifiant_unique = secrets.token_hex(4).upper()

    nom_pour_base = payload.nomEntreprise if payload.typeCompte == "entreprise" else payload.nomAdmin
    nom_base = f"compte_{_slugifier(nom_pour_base)}_{identifiant_unique.lower()}"
    nom_enregistre = payload.nomEntreprise if payload.typeCompte == "entreprise" else payload.nomAdmin
    secteur = payload.secteur if payload.typeCompte == "entreprise" else None

    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO entreprise
                   (type_compte, nom, secteur, identifiant_unique, nom_base, statut,
                    email_contact, telephone_contact, cgu_accepte_le, cgu_version)
                   VALUES (%s, %s, %s, %s, %s, 'en_attente', %s, %s, %s, %s)
                   RETURNING id""",
                (
                    payload.typeCompte, nom_enregistre, secteur, identifiant_unique, nom_base,
                    email, payload.telephone, datetime.now(timezone.utc), CGU_VERSION_ACTUELLE,
                ),
            )
            entreprise_id = cur.fetchone()[0]
        conn.commit()
    finally:
        pool_central.putconn(conn)

    mot_de_passe_hash = bcrypt.hashpw(payload.motDePasse.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    stocker_admin_temporaire(entreprise_id, payload.nomAdmin, email, mot_de_passe_hash)

    code_otp = generer_et_stocker_otp(entreprise_id)
    try:
        envoyer_code_otp(email, code_otp)
    except Exception:
        return JSONResponse(status_code=502, content={
            "message": "Inscription enregistrée, mais l'envoi de l'email a échoué. Réessayez l'envoi du code.",
            "entrepriseId": entreprise_id,
        })

    return {
        "entrepriseId": entreprise_id,
        "documentsRequis": DOCUMENTS_REQUIS[payload.typeCompte],
        "message": "Inscription reçue. Un code de vérification a été envoyé.",
    }


# --- Étape 2 : Vérification OTP ---
class OtpPayload(BaseModel):
    entrepriseId: int
    code: str


@router.post("/verifier-otp")
def verifier_otp_route(payload: OtpPayload):
    succes, raison = verifier_otp(payload.entrepriseId, payload.code)

    if not succes:
        messages = {
            "aucun_code_actif": "Aucun code actif. Demandez un nouveau code.",
            "trop_de_tentatives": "Trop de tentatives incorrectes. Demandez un nouveau code.",
            "expire": "Ce code a expiré. Demandez un nouveau code.",
            "code_incorrect": "Code incorrect.",
        }
        return JSONResponse(status_code=400, content={"message": messages.get(raison, "Code invalide."), "raison": raison})

    return {
        "message": "Vérification réussie.",
        "jetonInscription": _emettre_jeton_inscription(payload.entrepriseId),
    }


class RenvoiOtpPayload(BaseModel):
    entrepriseId: int


@router.post("/renvoyer-otp")
def renvoyer_otp(payload: RenvoiOtpPayload):
    if not peut_renvoyer_otp(payload.entrepriseId):
        attente = secondes_avant_renvoi(payload.entrepriseId)
        return JSONResponse(status_code=429, content={
            "message": f"Veuillez patienter {attente} secondes avant de redemander un code.",
            "secondesAvantRenvoi": attente,
        })

    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT email_contact FROM entreprise WHERE id = %s", (payload.entrepriseId,))
            ligne = cur.fetchone()
    finally:
        pool_central.putconn(conn)

    if not ligne:
        return JSONResponse(status_code=404, content={"message": "Entreprise introuvable."})

    code_otp = generer_et_stocker_otp(payload.entrepriseId)
    try:
        envoyer_code_otp(ligne[0], code_otp)
    except Exception:
        return JSONResponse(status_code=502, content={"message": "Échec de l'envoi de l'email. Réessayez."})

    return {"message": "Un nouveau code a été envoyé."}


# --- Étape 3 : Documents KYC, adaptés au type de compte ---
class KycPayload(BaseModel):
    entrepriseId: int
    documents: dict[str, str]  # ex: {"cin": "cin.pdf"} ou {"cin_gerant": "...", "patente": "...", "extrait_rne": "..."}


@router.post("/kyc")
def soumettre_kyc(payload: KycPayload, jeton: str | None = Header(None, alias="X-Jeton-Inscription")):
    if not _auto_validation_active():
        _exiger_jeton_inscription(payload.entrepriseId, jeton)
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT type_compte, statut FROM entreprise WHERE id = %s", (payload.entrepriseId,))
            ligne = cur.fetchone()
            if not ligne:
                return JSONResponse(status_code=404, content={"message": "Entreprise introuvable."})

            type_compte, statut_actuel = ligne
            if statut_actuel != "en_attente":
                return JSONResponse(status_code=409, content={
                    "message": "Ce dossier ne peut plus recevoir de documents.",
                })
            requis = set(DOCUMENTS_REQUIS[type_compte])
            fournis = set(payload.documents.keys())
            manquants = requis - fournis
            if manquants:
                return JSONResponse(status_code=400, content={
                    "message": f"Documents manquants pour ce type de compte : {', '.join(manquants)}.",
                })

            for type_doc, nom_fichier in payload.documents.items():
                cur.execute(
                    "INSERT INTO document_kyc (entreprise_id, type_document, nom_fichier) VALUES (%s, %s, %s)",
                    (payload.entrepriseId, type_doc, nom_fichier),
                )
        conn.commit()
    finally:
        pool_central.putconn(conn)

    # Dossier soumis : reste "en_attente" jusqu'à la validation administrative
    # (voir /valider et /refuser). Pour permettre de tester le parcours de
    # bout en bout sans interface Super Admin encore construite, on
    # auto-valide ici — à retirer une fois cette interface développée.
    if _auto_validation_active():
        _valider_dossier(payload.entrepriseId)

    return {"message": "Documents reçus. Votre dossier est en attente de validation."}


# --- Validation administrative (Super Admin) ---
class ValidationPayload(BaseModel):
    entrepriseId: int


@router.post("/valider")
def valider_dossier_route(payload: ValidationPayload, _: dict = Depends(exiger_super_admin)):
    if not _changer_statut_si(payload.entrepriseId, "valide", ("en_attente",)):
        return JSONResponse(status_code=409, content={
            "message": "Ce dossier ne peut pas être validé dans son état actuel.",
        })
    return {"message": "Dossier validé."}


@router.post("/refuser")
def refuser_dossier_route(payload: ValidationPayload, _: dict = Depends(exiger_super_admin)):
    if not _changer_statut_si(payload.entrepriseId, "refuse", ("en_attente", "valide")):
        return JSONResponse(status_code=409, content={
            "message": "Ce dossier ne peut pas être refusé dans son état actuel.",
        })
    return {"message": "Dossier refusé."}


def _valider_dossier(entreprise_id: int) -> bool:
    return _changer_statut_si(entreprise_id, "valide", ("en_attente",))


def _changer_statut_si(entreprise_id: int, nouveau_statut: str, statuts_autorises: tuple) -> bool:
    """Change le statut SEULEMENT si le statut actuel est autorise (une
    entreprise active ne peut jamais etre rebasculee par erreur ou abus)."""
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE entreprise SET statut = %s WHERE id = %s AND statut = ANY(%s) RETURNING id",
                (nouveau_statut, entreprise_id, list(statuts_autorises)),
            )
            modifie = cur.fetchone() is not None
        conn.commit()
    finally:
        pool_central.putconn(conn)
    return modifie


# --- Étape 4 : Choix de l'abonnement ---
class AbonnementPayload(BaseModel):
    entrepriseId: int
    plan: str  # "essai" | "standard" | "premium"


@router.post("/abonnement")
def choisir_abonnement(payload: AbonnementPayload, jeton: str | None = Header(None, alias="X-Jeton-Inscription")):
    if not _auto_validation_active():
        _exiger_jeton_inscription(payload.entrepriseId, jeton)
    if payload.plan not in PLANS_VALIDES:
        return JSONResponse(status_code=400, content={"message": "Plan d'abonnement invalide."})
    if not _statut_est(payload.entrepriseId, "valide"):
        return JSONResponse(status_code=400, content={"message": "Votre dossier doit être validé avant de choisir un abonnement."})

    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO abonnement (entreprise_id, type_plan, statut)
                   VALUES (%s, %s, 'en_attente')""",
                (payload.entrepriseId, payload.plan),
            )
        conn.commit()
    finally:
        pool_central.putconn(conn)

    return {"message": "Abonnement enregistré.", "requiertPaiement": payload.plan != "essai"}


# --- Étape 5 : Paiement + provisioning automatique ---
class PaiementPayload(BaseModel):
    entrepriseId: int


@router.post("/confirmer-paiement")
def confirmer_paiement(payload: PaiementPayload, acteur=Depends(_super_admin_optionnel)):
    # Le paiement est simule : tant qu'aucun prestataire reel n'est branche,
    # seule l'administration de la plateforme (ou le mode demo) peut confirmer.
    if acteur is None and not _auto_validation_active():
        raise HTTPException(status_code=403, detail="Le paiement doit être confirmé par l'administration de la plateforme.")
    return _activer_entreprise(payload.entrepriseId)


@router.post("/activer-essai")
def activer_essai(
    payload: PaiementPayload,
    acteur=Depends(_super_admin_optionnel),
    jeton: str | None = Header(None, alias="X-Jeton-Inscription"),
):
    if acteur is None and not _auto_validation_active():
        _exiger_jeton_inscription(payload.entrepriseId, jeton)
        if not _plan_est_essai(payload.entrepriseId):
            raise HTTPException(status_code=403, detail="Ce plan nécessite un paiement confirmé.")
    return _activer_entreprise(payload.entrepriseId)


def _activer_entreprise(entreprise_id: int):
    admin_temp = recuperer_admin_temporaire(entreprise_id)
    if not admin_temp:
        return JSONResponse(status_code=400, content={"message": "Aucune inscription en attente pour cette entreprise."})

    if not email_verifie(entreprise_id):
        return JSONResponse(status_code=400, content={"message": "L'adresse email n'a pas été vérifiée."})

    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT nom_base, statut FROM entreprise WHERE id = %s", (entreprise_id,))
            ligne = cur.fetchone()
    finally:
        pool_central.putconn(conn)

    if not ligne:
        return JSONResponse(status_code=404, content={"message": "Entreprise introuvable."})

    nom_base, statut_actuel = ligne
    if statut_actuel != "valide":
        return JSONResponse(status_code=409, content={
            "message": "Le dossier doit être validé avant l'activation.",
        })

    try:
        provisionner_entreprise(nom_base, admin_temp["nom"], admin_temp["email"], admin_temp["mot_de_passe_hash"], entreprise_id)
    except Exception:
        logging.getLogger("erp.onboarding").exception(
            "Provisioning en echec (entreprise %s)", entreprise_id
        )
        return JSONResponse(status_code=500, content={
            "message": "Erreur lors de la création de l'environnement. Réessayez plus tard ou contactez le support.",
        })

    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE abonnement SET statut = 'actif' WHERE entreprise_id = %s", (entreprise_id,))
        conn.commit()
    finally:
        pool_central.putconn(conn)

    _maj_statut(entreprise_id, "actif")
    supprimer_admin_temporaire(entreprise_id)

    return {"message": "Votre environnement ERP est prêt.", "nomBase": nom_base}


def _maj_statut(entreprise_id: int, statut: str) -> None:
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE entreprise SET statut = %s WHERE id = %s", (statut, entreprise_id))
        conn.commit()
    finally:
        pool_central.putconn(conn)


def _statut_est(entreprise_id: int, statut_attendu: str) -> bool:
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT statut FROM entreprise WHERE id = %s", (entreprise_id,))
            ligne = cur.fetchone()
    finally:
        pool_central.putconn(conn)
    return bool(ligne) and ligne[0] == statut_attendu
