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
import json
import logging
from typing import Annotated, Union

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.db import get_pool_entreprise
from app.security.auth_dependency import exiger_role_admin
from app.security.permissions import exiger_permission
from app.services import idp_integration
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

# Causes d'échec du modèle -> message utile pour l'utilisateur (aucune URL, aucun secret).
_MESSAGES_MODELE = {
    "unreachable": "Le modèle IA est injoignable depuis le serveur (Ollama est-il démarré et accessible ?).",
    "model_missing": ("Le modèle IA « {modele} » est introuvable sur le serveur : installez-le avec « ollama pull {modele} », "
                      "ou vérifiez que RAG_LLM_BASE_URL se termine par /v1."),
    "timeout": "Le modèle IA a mis trop de temps à répondre : réessayez avec un document plus court ou un modèle plus rapide.",
    "cooldown": "Le modèle IA vient d'échouer : nouvelle tentative possible dans quelques minutes.",
    "auth": "L'accès au modèle IA est refusé (clé invalide).",
    "quota": "Le quota du modèle IA est épuisé.",
    "rate_limit": "Le modèle IA est temporairement saturé : réessayez dans un instant.",
    "texte_vide": "Aucun texte n'a pu être lu dans ce document (image illisible ou OCR indisponible).",
    "sortie_invalide": "Le modèle a répondu dans un format inexploitable : réessayez, ou utilisez un modèle plus puissant.",
}

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
    # Structure libre (sections / champs / tableaux découverts) : assainie et bornée côté serveur.
    structure_libre: dict | None = None

    @field_validator("structure_libre")
    @classmethod
    def _taille_structure(cls, valeur):
        if valeur is not None and len(json.dumps(valeur, ensure_ascii=False)) > 200_000:
            raise ValueError("Structure trop volumineuse.")
        return valeur


class ChoixLigne(_Strict):
    index: int = Field(ge=0, le=1000)
    produit_id: int | None = Field(default=None, ge=1)
    creer: bool = False


class ChoixIntegration(_Strict):
    fournisseur_id: int | None = Field(default=None, ge=1)
    creer_fournisseur: bool = False
    lignes: list[ChoixLigne] = Field(max_length=1000)


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

    pool = _pool(utilisateur)
    champs_connus = stockage.noms_champs_personnalises(pool)
    options = {"champs_connus": champs_connus} if champs_connus else {}
    try:
        resultat = structuration.traiter_document(contenu, nom, **options)
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
            502,
            _MESSAGES_MODELE.get(getattr(exc, "code", None), "").replace("{modele}", structuration.nom_modele())
            or "Le modèle d'analyse n'a pas pu lire ce document. Réessayez plus tard.") from exc

    try:
        depot = stockage.enregistrer_depot(
            pool, resultat, contenu, nom,
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


@router.get("/documents/{document_id}/integration")
def proposition_integration(document_id: int, utilisateur: dict = Depends(utilisateur_idp)):
    """Ce que l'intégration dans Achats ferait pour ce document validé (aucune écriture)."""
    try:
        return idp_integration.proposer(_pool(utilisateur), document_id)
    except stockage.StockageErreur as exc:
        raise _http(exc)


@router.post("/documents/{document_id}/integrer")
def integrer_document(document_id: int, choix: ChoixIntegration,
                      utilisateur: dict = Depends(exiger_permission("achats", "creer"))):
    """Crée dans Achats le document d'achat correspondant, après confirmation des choix par l'utilisateur."""
    if utilisateur.get("type") != "interne" or not utilisateur.get("nomBase"):
        raise HTTPException(403, "Réservé aux utilisateurs internes de l'entreprise.")
    try:
        resultat = idp_integration.integrer(
            _pool(utilisateur), utilisateur["nomBase"], document_id, choix.model_dump(), _acteur(utilisateur))
    except idp_integration.IntegrationErreur as exc:
        raise HTTPException(exc.statut, exc.detail) from exc
    except stockage.StockageErreur as exc:
        raise _http(exc)
    from app.routers.notifications import notifier_action      # import tardif : évite un cycle au démarrage
    notifier_action(utilisateur, "Document intégré dans Achats",
                    f"Le document IDP n°{document_id} a créé {resultat['numero']}.", "/achats")
    return resultat


@router.get("/champs-personnalises")
def champs_personnalises(utilisateur: dict = Depends(utilisateur_idp)):
    """Champs découverts par l'IA dans des documents validés et réutilisés ensuite."""
    return stockage.lister_champs_personnalises(_pool(utilisateur))


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
