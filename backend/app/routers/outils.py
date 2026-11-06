"""Services transversaux réutilisables par les différents modules et le frontend.

Pour l'instant : conversion d'un montant en toutes lettres (fr, en, ar ;
MAD, EUR, USD). La route exige une session valide, comme le reste de l'API ;
elle ne lit ni n'écrit aucune donnée d'entreprise.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.security.auth_dependency import utilisateur_connecte
from app.services import montant_lettres as ml

router = APIRouter(prefix="/api/outils", tags=["outils"])


@router.get("/montant-en-lettres")
def montant_en_lettres(
    montant: str = Query(..., min_length=1, max_length=40),
    devise: str = Query("MAD", max_length=8),
    langue: str = Query("fr", max_length=8),
    utilisateur: dict = Depends(utilisateur_connecte),
):
    try:
        valeur = ml.normaliser_montant(montant)
        texte = ml.montant_en_lettres(valeur, devise, langue)
        libelle = ml.libelle_montant_en_lettres(langue)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "montant": format(valeur, "f"),
        "devise": ml.normaliser_devise(devise).code,
        "langue": ml.normaliser_langue(langue),
        "libelle": libelle,
        "texte": texte,
    }


@router.get("/montant-en-lettres/devises")
def devises_prises_en_charge(utilisateur: dict = Depends(utilisateur_connecte)):
    return {"devises": sorted(ml.DEVISES), "langues": list(ml.LANGUES)}
