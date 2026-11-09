from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services import boutons_flottants as r


class ConfigPayload(BaseModel):
    actif: bool = True
    position: Literal[r.POSITIONS_PRINCIPAL] = "auto"
    taille: Literal[r.TAILLES] = "moyen"
    couleur: str | None = None
    icone: Literal[r.ICONES] = "headset"

    @field_validator("couleur", mode="before")
    @classmethod
    def couleur_ok(cls, v):
        v = (v or "").strip() or None
        if not r.couleur_valide(v):
            raise ValueError("Couleur invalide : format #RRGGBB attendu.")
        return v.lower() if v else None


class BoutonPayload(BaseModel):
    cle: str | None = None
    titres: dict[str, str]
    icone: Literal[r.ICONES]
    couleur: str | None = None
    taille: Literal[r.TAILLES] = "moyen"
    placement: Literal[r.PLACEMENTS] = "menu"
    position: Literal[r.POSITIONS] | None = None
    ordre: int = Field(default=100, ge=0, le=9999)
    actif: bool = True
    action: Literal[r.ACTIONS]
    cible: str | None = None
    nouvel_onglet: bool = False
    audience: Literal[r.AUDIENCES] = "tous"
    profils: list[Literal[r.PROFILS]] = Field(default_factory=list)
    appareils: Literal[r.APPAREILS] = "tous"
    routes_incluses: list[str] = Field(default_factory=list)
    routes_exclues: list[str] = Field(default_factory=list)
    affiche_du: datetime | None = None
    affiche_jusqu_au: datetime | None = None

    @field_validator("cle", mode="before")
    @classmethod
    def cle_ok(cls, v):
        v = (v or "").strip().lower() or None
        if v is not None and not r.cle_valide(v):
            raise ValueError("Identifiant invalide : 2 à 39 caractères (a-z, 0-9, - et _).")
        return v

    @field_validator("titres")
    @classmethod
    def titres_ok(cls, v):
        propres = {}
        for langue, texte in v.items():
            if langue not in r.LANGUES:
                raise ValueError(f"Langue inconnue « {langue} ».")
            texte = (texte or "").strip()
            if texte:
                if len(texte) > 40:
                    raise ValueError("Un titre ne peut pas dépasser 40 caractères.")
                propres[langue] = texte
        if "fr" not in propres:
            raise ValueError("Le titre en français est obligatoire.")
        return propres

    @field_validator("couleur", mode="before")
    @classmethod
    def couleur_ok(cls, v):
        v = (v or "").strip() or None
        if not r.couleur_valide(v):
            raise ValueError("Couleur invalide : format #RRGGBB attendu.")
        return v.lower() if v else None

    @field_validator("routes_incluses", "routes_exclues", mode="before")
    @classmethod
    def prefixes_ok(cls, v):
        v = [str(x).strip() for x in (v or []) if str(x).strip()]
        erreur = r.verifier_prefixes(v)
        if erreur:
            raise ValueError(erreur)
        return list(dict.fromkeys(v))

    @field_validator("profils")
    @classmethod
    def profils_uniques(cls, v):
        return list(dict.fromkeys(v))

    @model_validator(mode="after")
    def coherence(self):
        erreur = r.verifier_cible(self.action, self.cible, self.nouvel_onglet)
        if erreur:
            raise ValueError(erreur)
        self.cible = r.normaliser_cible(self.action, self.cible)
        if self.placement == "libre" and not self.position:
            raise ValueError("Choisissez la position d'un bouton libre.")
        if self.placement == "menu":
            self.position = None
        if self.affiche_du and self.affiche_jusqu_au and self.affiche_jusqu_au <= self.affiche_du:
            raise ValueError("La date de fin doit suivre la date de début.")
        if self.audience == "public" and self.profils:
            raise ValueError("Un bouton réservé aux visiteurs ne peut pas cibler de profil connecté.")
        if self.action in ("notifications", "assistant") and self.audience == "public":
            raise ValueError("Cette action nécessite un utilisateur connecté.")
        return self


class OrdrePayload(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)

    @field_validator("ids")
    @classmethod
    def uniques(cls, v):
        if len(set(v)) != len(v):
            raise ValueError("Identifiants en double.")
        return v


class ActifPayload(BaseModel):
    actif: bool
