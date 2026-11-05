"""Routes IDP : dépôt, consultation, correction, validation et rejet de documents.

Sécurité (mêmes principes que assistant_documents) :
- authentification Bearer + permission RBAC revérifiée en base ;
- la base entreprise vient du JWT signé, jamais d'un paramètre client ;
- le nom de fichier envoyé ne sert jamais de chemin MinIO (clé = empreinte) ;
- l'original n'est jamais exposé par une URL publique : téléchargement
  authentifié uniquement, en pièce jointe, sans interprétation par le navigateur ;
- validation et rejet sont réservés à l'administrateur de l'entreprise.

Droits : dépôt, consultation, correction et téléchargement exigent la permission
documents.creer (celle déjà utilisée pour l'import RAG) ; valider et rejeter
exigent le rôle administrateur. Pour affiner (par exemple une permission
dédiée), ne changer que `_acces` ci-dessous et les dépendances des deux routes
de décision.
"""
import logging
from typing import Annotated, Union

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.db import get_pool_entreprise
from app.security.auth_dependency import exiger_role_admin
from app.security.permissions import exiger_permission
from app.services import idp_stockage as stockage
from app.services import idp_structuration as structuration
from app.services.idp_extraction import (
    TAILLE_MAX_OCTETS,
    DocumentIllisible,
    FichierTropVolumineux,
    FormatNonSupporte,
)

logger = logging.getLogger("erp.idp")

router = APIRouter(prefix="/api/idp", tags=["idp"])

_acces = exiger_permission("documents", "creer")

_EXTENSIONS_TELECHARGEMENT = {"pdf", "docx", "xlsx", "pptx", "csv", "xml", "json", "txt"}


def utilisateur_idp(utilisateur: dict = Depends(_acces)) -> dict:
    """Utilisateur interne, avec la permission documents.creer."""
    if utilisateur.get("type") != "interne" or not utilisateur.get("nomBase"):
        raise HTTPException(403, "Réservé aux utilisateurs internes de l'entreprise.")
    return utilisateur


def _pool(utilisateur: dict):
    return get_pool_entreprise(utilisateur["nomBase"])


def _acteur(utilisateur: dict) -> str | None:
    identifiant = utilisateur.get("id")
    return None if identifiant is None else str(identifiant)


def _http(exc: Exception) -> HTTPException:
    """Traduit une erreur métier du stockage en erreur HTTP."""
    if isinstance(exc, stockage.DocumentIntrouvable):
        return HTTPException(404, str(exc))
    if isinstance(exc, (stockage.TransitionInterdite, stockage.ValidationBloquee)):
        return HTTPException(409, str(exc))
    if isinstance(exc, stockage.StockageFichierIndisponible):
        logger.error("Stockage MinIO indisponible : %s", exc)
        return HTTPException(503, "Le stockage des documents est momentanément indisponible.")
    logger.exception("Erreur inattendue dans le stockage IDP")
    return HTTPException(500, "Erreur interne.")


# --------------------------------------------------------------------------
# Schémas des corps de requête
# --------------------------------------------------------------------------

Texte = Annotated[str, StringConstraints(max_length=300)]
Valeur = Union[Texte, int, float, None]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FournisseurCorrection(_Strict):
    nom: Valeur = None
    ice: Valeur = None
    identifiant_fiscal: Valeur = None


class LigneCorrection(_Strict):
    designation: Valeur = None
    quantite: Valeur = None
    prix_unitaire: Valeur = None
    remise: Valeur = None
    total: Valeur = None


class Corrections(_Strict):
    """Seuls les champs envoyés sont modifiés ; null efface une valeur."""
    type_document: Valeur = None
    numero: Valeur = None
    date: Valeur = None
    date_echeance: Valeur = None
    devise: Valeur = None
    fournisseur: FournisseurCorrection | None = None
    lignes: list[LigneCorrection] | None = Field(default=None, max_length=500)
    total_ht: Valeur = None
    total_tva: Valeur = None
    total_ttc: Valeur = None
    taux_tva: Valeur = None


class Rejet(_Strict):
    motif: str = Field(min_length=1, max_length=stockage.LONGUEUR_MAX_MOTIF)


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@router.post("/documents", status_code=201)
def deposer_document(
    fichier: UploadFile = File(...),
    utilisateur: dict = Depends(utilisateur_idp),
):
    # Lecture bornée : au plus limite+1 octets, jamais un gros fichier en mémoire.
    contenu = fichier.file.read(TAILLE_MAX_OCTETS + 1)
    if len(contenu) > TAILLE_MAX_OCTETS:
        raise HTTPException(
            413, f"Fichier trop volumineux (maximum {TAILLE_MAX_OCTETS // (1024 * 1024)} Mo).")
    if not contenu:
        raise HTTPException(422, "Le fichier est vide.")
    nom = fichier.filename or ""

    try:
        resultat = structuration.traiter_document(contenu, nom)
    except FichierTropVolumineux as exc:
        raise HTTPException(413, str(exc)) from exc
    except FormatNonSupporte as exc:
        raise HTTPException(415, str(exc)) from exc
    except DocumentIllisible as exc:
        raise HTTPException(422, str(exc)) from exc
    except structuration.StructurationIndisponible as exc:
        logger.warning("Analyse automatique non configurée : %s", exc)
        raise HTTPException(503, "L'analyse automatique des documents n'est pas configurée.") from exc
    except structuration.StructurationEchouee as exc:
        logger.exception("Le modèle n'a pas pu structurer le document")
        raise HTTPException(
            502, "Le modèle d'analyse n'a pas pu lire ce document. Réessayez plus tard.") from exc

    try:
        depot = stockage.enregistrer_depot(
            _pool(utilisateur), resultat, contenu, nom,
            prefixe=utilisateur["nomBase"], depose_par=_acteur(utilisateur),
        )
    except stockage.StockageErreur as exc:
        raise _http(exc) from exc

    return {
        **depot,
        "format": resultat["format"],
        "ocr_utilise": resultat["ocr_utilise"],
        "donnees": resultat["donnees"],
        "anomalies": resultat["anomalies"],
        "resume": resultat["resume"],
        "avertissements": resultat["avertissements"],
    }


@router.get("/documents")
def lister_documents(
    statut: str | None = Query(default=None, pattern="^(brouillon|valide|rejete)$"),
    limite: int = Query(default=50, ge=1, le=200),
    decalage: int = Query(default=0, ge=0),
    utilisateur: dict = Depends(utilisateur_idp),
):
    return stockage.lister(_pool(utilisateur), statut=statut, limite=limite, decalage=decalage)


@router.get("/documents/{document_id}")
def detail_document(document_id: int, utilisateur: dict = Depends(utilisateur_idp)):
    try:
        document = stockage.obtenir(_pool(utilisateur), document_id)
    except stockage.StockageErreur as exc:
        raise _http(exc) from exc
    document.pop("cle_stockage", None)    # détail interne, jamais exposé
    return document


@router.patch("/documents/{document_id}")
def corriger_document(
    document_id: int,
    corrections: Corrections,
    utilisateur: dict = Depends(utilisateur_idp),
):
    champs = corrections.model_dump(exclude_unset=True)
    try:
        return stockage.corriger(_pool(utilisateur), document_id, champs, _acteur(utilisateur))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except stockage.StockageErreur as exc:
        raise _http(exc) from exc


@router.post("/documents/{document_id}/valider")
def valider_document(document_id: int, utilisateur: dict = Depends(exiger_role_admin)):
    try:
        return stockage.valider(_pool(utilisateur), document_id, _acteur(utilisateur))
    except stockage.StockageErreur as exc:
        raise _http(exc) from exc


@router.post("/documents/{document_id}/rejeter")
def rejeter_document(
    document_id: int,
    rejet: Rejet,
    utilisateur: dict = Depends(exiger_role_admin),
):
    try:
        return stockage.rejeter(_pool(utilisateur), document_id, rejet.motif, _acteur(utilisateur))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except stockage.StockageErreur as exc:
        raise _http(exc) from exc


@router.get("/documents/{document_id}/fichier")
def telecharger_fichier(document_id: int, utilisateur: dict = Depends(utilisateur_idp)):
    """Original du document, en pièce jointe (jamais interprété par le navigateur)."""
    try:
        document = stockage.obtenir(_pool(utilisateur), document_id)
        contenu = stockage.lire_fichier(document["cle_stockage"])
    except stockage.StockageErreur as exc:
        raise _http(exc) from exc
    format_document = str(document.get("format") or "")
    extension = format_document if format_document in _EXTENSIONS_TELECHARGEMENT else "bin"
    return Response(
        content=contenu,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="document-{document_id}.{extension}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
