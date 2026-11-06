"""Prospects : création, vérification et détection de doublons, suivi commercial daté,
conversion en client, archivage / réactivation (sans jamais supprimer l'historique).

Permissions (module « prospects ») :
  consulter → liste, fiche, historique, vérification des doublons
  creer     → nouveau prospect, nouveau suivi
  modifier  → modification de la fiche, changement de statut
  valider   → conversion en client
  supprimer → archivage / réactivation (aucune suppression physique)
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg2.errors import UniqueViolation

from app.schemas.prospects import (
    ArchivagePayload, ChangementStatutPayload, ConversionPayload, ProspectPayload, SuiviPayload,
)
from app.security.permissions import actions_autorisees, exiger_permission
from app.services import prospects as regles
from app.services.suivi_commercial import ecrire_evenement, lire_historique_prospect, rechercher_doublons
from app.services.transactions import transaction_entreprise

router = APIRouter(prefix="/api/prospects", tags=["prospects"])

_COLONNES = """p.id, p.nom, p.contact, p.email, p.telephone, p.adresse, p.source, p.statut, p.besoin,
       p.responsable_id, TRIM(COALESCE(r.prenom, '') || ' ' || COALESCE(r.nom, '')) AS responsable_nom,
       p.client_id, c.nom AS client_nom, p.date_conversion, p.prochaine_relance_le,
       p.derniere_interaction_le, p.archive, p.archive_le, p.archive_motif,
       p.cree_le, p.mis_a_jour_le,
       (p.prochaine_relance_le IS NOT NULL AND p.prochaine_relance_le < CURRENT_DATE
        AND NOT p.archive AND p.statut IN ('nouveau', 'contacte', 'qualifie')) AS relance_en_retard"""
_JOINTURES = "FROM prospect p LEFT JOIN utilisateur r ON r.id = p.responsable_id LEFT JOIN client c ON c.id = p.client_id"
_TOLERANCE_HORLOGE = timedelta(minutes=5)


def _dicts(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _fiche(cur, prospect_id: int, verrouiller: bool = False) -> dict:
    """Charge un prospect ; verrouille la ligne (FOR UPDATE OF p) pour les opérations d'écriture."""
    cur.execute(
        f"SELECT {_COLONNES} {_JOINTURES} WHERE p.id = %s" + (" FOR UPDATE OF p" if verrouiller else ""),
        (prospect_id,),
    )
    lignes = _dicts(cur)
    if not lignes:
        raise HTTPException(status_code=404, detail="Prospect introuvable.")
    return lignes[0]


def _exiger_modifiable(prospect: dict):
    if prospect["archive"]:
        raise HTTPException(status_code=409, detail="Prospect archivé : réactivez-le avant toute modification.")
    if prospect["statut"] == "converti":
        raise HTTPException(status_code=409, detail="Prospect déjà converti : poursuivez le suivi sur la fiche client.")


def _responsable(cur, responsable_id, utilisateur) -> int | None:
    if responsable_id is None:
        return utilisateur.get("id")
    cur.execute("SELECT 1 FROM utilisateur WHERE id = %s AND actif", (responsable_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=400, detail="Le responsable choisi n'existe pas ou est désactivé.")
    return responsable_id


def _publier_doublon(d: dict) -> dict:
    return {k: d.get(k) for k in ("entite", "id", "nom", "email", "telephone", "archive", "statut", "motifs", "niveau")}


def _controle_doublons(doublons: list[dict], confirme: bool) -> JSONResponse | None:
    """409 si un doublon fort existe (jamais contournable) ou si un doublon possible n'est pas confirmé."""
    if not doublons:
        return None
    fort = regles.contient_doublon_fort(doublons)
    if not fort and confirme:
        return None
    return JSONResponse(
        status_code=409,
        content=jsonable_encoder({
            "detail": regles.message_doublons(doublons),
            "code": "DOUBLON_FORT" if fort else "DOUBLON_POSSIBLE",
            "confirmable": not fort,
            "doublons": [_publier_doublon(d) for d in doublons],
        }),
    )


def _valeurs(payload: ProspectPayload, responsable_id) -> dict:
    return {
        "nom": payload.nom, "contact": payload.contact, "email": payload.email, "telephone": payload.telephone,
        "adresse": payload.adresse, "source": payload.source, "besoin": payload.besoin,
        "responsable_id": responsable_id,
    }


def _conflit_unicite(exc: UniqueViolation):
    champ = "adresse e-mail" if "email" in (exc.diag.constraint_name or "") else "numéro de téléphone"
    return HTTPException(status_code=409, detail=f"Un prospect utilise déjà cette {champ}.")


# --------------------------------------------------------------------------
@router.get("/permissions")
def mes_permissions(utilisateur=Depends(exiger_permission("prospects", "consulter"))):
    return {"module": "prospects", "actions": actions_autorisees(utilisateur, "prospects")}


@router.get("/verification-doublon")
def verifier_doublons(
    nom: str | None = None, email: str | None = None, telephone: str | None = None,
    exclure_id: int | None = None,
    utilisateur=Depends(exiger_permission("prospects", "consulter")),
):
    """Contrôle en direct (avant enregistrement) parmi les prospects ET les clients."""
    with transaction_entreprise(utilisateur) as cur:
        doublons = rechercher_doublons(cur, nom=nom, email=email, telephone=telephone, exclure_prospect_id=exclure_id)
    return {"doublons": [_publier_doublon(d) for d in doublons]}


@router.get("")
def lister_prospects(
    statut: str | None = Query(default=None, pattern="^(nouveau|contacte|qualifie|perdu|converti)$"),
    archives: str = Query(default="actifs", pattern="^(actifs|archives|tous)$"),
    q: str | None = Query(default=None, max_length=150),
    limite: int = Query(default=200, ge=1, le=500),
    decalage: int = Query(default=0, ge=0),
    utilisateur=Depends(exiger_permission("prospects", "consulter")),
):
    filtres, params = [], []
    if archives == "actifs":
        filtres.append("NOT p.archive")
    elif archives == "archives":
        filtres.append("p.archive")
    if statut:
        filtres.append("p.statut = %s")
        params.append(statut)
    if q and q.strip():
        motif = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        filtres.append("(p.nom ILIKE %s OR p.contact ILIKE %s OR p.email ILIKE %s OR p.telephone ILIKE %s)")
        params += [motif] * 4
    where = ("WHERE " + " AND ".join(filtres)) if filtres else ""
    with transaction_entreprise(utilisateur) as cur:
        cur.execute(f"SELECT COUNT(*) FROM prospect p {where}", params)
        total = cur.fetchone()[0]
        cur.execute(
            f"SELECT {_COLONNES} {_JOINTURES} {where} ORDER BY p.cree_le DESC, p.id DESC LIMIT %s OFFSET %s",
            [*params, limite, decalage],
        )
        return {"prospects": _dicts(cur), "total": total}


@router.post("")
def creer_prospect(payload: ProspectPayload, utilisateur=Depends(exiger_permission("prospects", "creer"))):
    try:
        with transaction_entreprise(utilisateur) as cur:
            responsable_id = _responsable(cur, payload.responsable_id, utilisateur)
            doublons = rechercher_doublons(cur, nom=payload.nom, email=payload.email, telephone=payload.telephone)
            refus = _controle_doublons(doublons, payload.confirmer_doublon)
            if refus:
                return refus
            valeurs = _valeurs(payload, responsable_id)
            cur.execute(
                """
                INSERT INTO prospect (nom, contact, email, telephone, adresse, source, besoin, responsable_id, cree_par)
                VALUES (%(nom)s, %(contact)s, %(email)s, %(telephone)s, %(adresse)s, %(source)s, %(besoin)s,
                        %(responsable_id)s, %(cree_par)s)
                RETURNING id
                """,
                {**valeurs, "cree_par": utilisateur.get("id")},
            )
            prospect_id = cur.fetchone()[0]
            ecrire_evenement(cur, "prospect", prospect_id, "creation", utilisateur,
                             contenu="Prospect créé.", details={"source": payload.source})
            prospect = _fiche(cur, prospect_id)
    except UniqueViolation as exc:
        raise _conflit_unicite(exc)
    return {"prospect": prospect, "message": "Prospect créé avec succès."}


@router.get("/{prospect_id}")
def obtenir_prospect(prospect_id: int, utilisateur=Depends(exiger_permission("prospects", "consulter"))):
    with transaction_entreprise(utilisateur) as cur:
        return _fiche(cur, prospect_id)


@router.patch("/{prospect_id}")
def modifier_prospect(prospect_id: int, payload: ProspectPayload,
                      utilisateur=Depends(exiger_permission("prospects", "modifier"))):
    try:
        with transaction_entreprise(utilisateur) as cur:
            actuel = _fiche(cur, prospect_id, verrouiller=True)
            _exiger_modifiable(actuel)
            responsable_id = _responsable(cur, payload.responsable_id, utilisateur) if payload.responsable_id else actuel["responsable_id"]
            doublons = rechercher_doublons(cur, nom=payload.nom, email=payload.email, telephone=payload.telephone,
                                           exclure_prospect_id=prospect_id)
            refus = _controle_doublons(doublons, payload.confirmer_doublon)
            if refus:
                return refus
            valeurs = _valeurs(payload, responsable_id)
            changements = regles.differences(actuel, valeurs)
            if not changements:
                return {"prospect": actuel, "message": "Aucune modification."}
            cur.execute(
                """
                UPDATE prospect SET nom=%(nom)s, contact=%(contact)s, email=%(email)s, telephone=%(telephone)s,
                       adresse=%(adresse)s, source=%(source)s, besoin=%(besoin)s, responsable_id=%(responsable_id)s,
                       mis_a_jour_le=NOW()
                WHERE id=%(id)s
                """,
                {**valeurs, "id": prospect_id},
            )
            ecrire_evenement(cur, "prospect", prospect_id, "modification", utilisateur,
                             contenu="Champs modifiés : " + ", ".join(changements), details={"changements": changements})
            prospect = _fiche(cur, prospect_id)
    except UniqueViolation as exc:
        raise _conflit_unicite(exc)
    return {"prospect": prospect, "message": "Prospect modifié avec succès."}


@router.post("/{prospect_id}/statut")
def changer_statut(prospect_id: int, payload: ChangementStatutPayload,
                   utilisateur=Depends(exiger_permission("prospects", "modifier"))):
    with transaction_entreprise(utilisateur) as cur:
        actuel = _fiche(cur, prospect_id, verrouiller=True)
        _exiger_modifiable(actuel)
        if payload.statut == actuel["statut"]:
            raise HTTPException(status_code=409, detail="Le prospect a déjà ce statut.")
        if not regles.transition_autorisee(actuel["statut"], payload.statut):
            raise HTTPException(status_code=409, detail=f"Passage de « {actuel['statut']} » à « {payload.statut} » non autorisé.")
        cur.execute("UPDATE prospect SET statut = %s, mis_a_jour_le = NOW() WHERE id = %s", (payload.statut, prospect_id))
        ecrire_evenement(cur, "prospect", prospect_id, "statut", utilisateur, contenu=payload.commentaire,
                         details={"avant": actuel["statut"], "apres": payload.statut})
        return {"prospect": _fiche(cur, prospect_id), "message": "Statut mis à jour."}


@router.post("/{prospect_id}/suivis")
def ajouter_suivi(prospect_id: int, payload: SuiviPayload,
                  utilisateur=Depends(exiger_permission("prospects", "creer"))):
    maintenant = datetime.now(timezone.utc)
    date_evenement = payload.date_evenement or maintenant
    if date_evenement > maintenant + _TOLERANCE_HORLOGE:
        raise HTTPException(status_code=400, detail="La date du suivi ne peut pas être dans le futur.")
    if payload.prochaine_relance and payload.prochaine_relance < date_evenement.date():
        raise HTTPException(status_code=400, detail="La prochaine relance ne peut pas précéder la date du suivi.")
    with transaction_entreprise(utilisateur) as cur:
        actuel = _fiche(cur, prospect_id, verrouiller=True)
        _exiger_modifiable(actuel)
        suivi_id = ecrire_evenement(
            cur, "prospect", prospect_id, payload.type_evenement, utilisateur, contenu=payload.contenu,
            details={"prochaine_relance": payload.prochaine_relance} if payload.prochaine_relance else {},
            date_evenement=date_evenement,
        )
        cur.execute(
            """
            UPDATE prospect
            SET derniere_interaction_le = GREATEST(COALESCE(derniere_interaction_le, %s), %s),
                prochaine_relance_le = COALESCE(%s, prochaine_relance_le),
                mis_a_jour_le = NOW()
            WHERE id = %s
            """,
            (date_evenement, date_evenement, payload.prochaine_relance, prospect_id),
        )
        return {"suivi_id": suivi_id, "prospect": _fiche(cur, prospect_id), "message": "Suivi enregistré."}


@router.get("/{prospect_id}/historique")
def historique(prospect_id: int, limite: int = Query(default=200, ge=1, le=500), decalage: int = Query(default=0, ge=0),
               utilisateur=Depends(exiger_permission("prospects", "consulter"))):
    with transaction_entreprise(utilisateur) as cur:
        _fiche(cur, prospect_id)
        return {"historique": lire_historique_prospect(cur, prospect_id, limite, decalage)}


@router.post("/{prospect_id}/convertir")
def convertir_en_client(prospect_id: int, payload: ConversionPayload,
                        utilisateur=Depends(exiger_permission("prospects", "valider"))):
    with transaction_entreprise(utilisateur) as cur:
        prospect = _fiche(cur, prospect_id, verrouiller=True)
        if prospect["archive"]:
            raise HTTPException(status_code=409, detail="Prospect archivé : réactivez-le avant de le convertir.")
        if prospect["statut"] == "converti":
            raise HTTPException(status_code=409, detail="Ce prospect a déjà été converti en client.")
        if not regles.peut_etre_converti(prospect["statut"], prospect["archive"]):
            raise HTTPException(status_code=409, detail="Un prospect perdu doit être rouvert avant d'être converti.")

        if payload.client_existant_id:
            cur.execute("SELECT id, nom, archive FROM client WHERE id = %s FOR UPDATE", (payload.client_existant_id,))
            client = cur.fetchone()
            if not client:
                raise HTTPException(status_code=404, detail="Client introuvable.")
            if client[2]:
                raise HTTPException(status_code=409, detail="Ce client est archivé : réactivez-le avant de lui rattacher le prospect.")
            client_id, mode = client[0], "rattachement"
        else:
            doublons = regles.elever_nom_identique_client(rechercher_doublons(
                cur, nom=prospect["nom"], email=prospect["email"], telephone=prospect["telephone"],
                inclure_prospects=False))
            refus = _controle_doublons(doublons, payload.confirmer_doublon)
            if refus:
                return refus
            cur.execute(
                "INSERT INTO client (nom, email, telephone, adresse) VALUES (%s, %s, %s, %s) RETURNING id",
                (prospect["nom"], prospect["email"], prospect["telephone"], prospect["adresse"]),
            )
            client_id, mode = cur.fetchone()[0], "creation"

        cur.execute(
            """
            UPDATE prospect SET statut = 'converti', client_id = %s, date_conversion = NOW(),
                   prochaine_relance_le = NULL, mis_a_jour_le = NOW()
            WHERE id = %s
            """,
            (client_id, prospect_id),
        )
        ecrire_evenement(cur, "prospect", prospect_id, "conversion", utilisateur,
                         contenu=("Converti en nouveau client." if mode == "creation" else "Rattaché à un client existant."),
                         details={"client_id": client_id, "mode": mode, "statut_avant": prospect["statut"]})
        ecrire_evenement(cur, "client", client_id, "conversion", utilisateur,
                         contenu=f"Issu du prospect « {prospect['nom']} » (n° {prospect_id}).",
                         details={"prospect_id": prospect_id, "mode": mode})
        return {"prospect": _fiche(cur, prospect_id), "client_id": client_id,
                "message": "Prospect converti en client." if mode == "creation" else "Prospect rattaché au client."}


@router.post("/{prospect_id}/archiver")
def archiver(prospect_id: int, payload: ArchivagePayload,
             utilisateur=Depends(exiger_permission("prospects", "supprimer"))):
    with transaction_entreprise(utilisateur) as cur:
        prospect = _fiche(cur, prospect_id, verrouiller=True)
        if prospect["archive"]:
            raise HTTPException(status_code=409, detail="Ce prospect est déjà archivé.")
        cur.execute(
            "UPDATE prospect SET archive = TRUE, archive_le = NOW(), archive_motif = %s, archive_par = %s, mis_a_jour_le = NOW() WHERE id = %s",
            (payload.motif, utilisateur.get("id"), prospect_id),
        )
        ecrire_evenement(cur, "prospect", prospect_id, "archivage", utilisateur, contenu=payload.motif)
        return {"prospect": _fiche(cur, prospect_id), "message": "Prospect archivé. Son historique est conservé."}


@router.post("/{prospect_id}/reactiver")
def reactiver(prospect_id: int, utilisateur=Depends(exiger_permission("prospects", "supprimer"))):
    with transaction_entreprise(utilisateur) as cur:
        prospect = _fiche(cur, prospect_id, verrouiller=True)
        if not prospect["archive"]:
            raise HTTPException(status_code=409, detail="Ce prospect n'est pas archivé.")
        cur.execute(
            "UPDATE prospect SET archive = FALSE, archive_le = NULL, archive_motif = NULL, archive_par = NULL, mis_a_jour_le = NOW() WHERE id = %s",
            (prospect_id,),
        )
        ecrire_evenement(cur, "prospect", prospect_id, "reactivation", utilisateur,
                         contenu=f"Réactivé (statut conservé : {prospect['statut']}).")
        return {"prospect": _fiche(cur, prospect_id), "message": "Prospect réactivé."}
