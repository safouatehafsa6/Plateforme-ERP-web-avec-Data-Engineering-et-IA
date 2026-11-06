from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.clients import ClientPayload

SourceProspect = Literal["site_web", "recommandation", "salon", "appel_entrant", "reseaux_sociaux", "campagne", "autre"]
StatutProspect = Literal["nouveau", "contacte", "qualifie", "perdu"]
TypeSuivi = Literal["appel", "email", "rendez_vous", "note", "relance"]


def _texte_optionnel(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    return value


class ProspectPayload(ClientPayload):
    """Création / modification d'un prospect : mêmes contrôles que le client, plus un moyen de contact obligatoire."""

    contact: str | None = Field(default=None, max_length=150)
    source: SourceProspect = "autre"
    besoin: str | None = Field(default=None, max_length=2000)
    responsable_id: int | None = Field(default=None, ge=1)
    confirmer_doublon: bool = False

    @field_validator("contact", "besoin", mode="before")
    @classmethod
    def nettoyer_textes(cls, value):
        return _texte_optionnel(value)

    @model_validator(mode="after")
    def exiger_un_moyen_de_contact(self):
        if not self.email and not self.telephone:
            raise ValueError("Renseignez au moins une adresse e-mail ou un numéro de téléphone.")
        return self


class ChangementStatutPayload(BaseModel):
    statut: StatutProspect
    commentaire: str | None = Field(default=None, max_length=2000)

    @field_validator("commentaire", mode="before")
    @classmethod
    def nettoyer(cls, value):
        return _texte_optionnel(value)

    @model_validator(mode="after")
    def motif_obligatoire_si_perdu(self):
        if self.statut == "perdu" and not self.commentaire:
            raise ValueError("Indiquez le motif de la perte du prospect.")
        return self


class SuiviPayload(BaseModel):
    type_evenement: TypeSuivi
    contenu: str = Field(min_length=1, max_length=4000)
    date_evenement: datetime | None = None
    prochaine_relance: date | None = None

    @field_validator("contenu", mode="before")
    @classmethod
    def nettoyer_contenu(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("date_evenement")
    @classmethod
    def date_avec_fuseau(cls, value):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class ConversionPayload(BaseModel):
    client_existant_id: int | None = Field(default=None, ge=1)
    confirmer_doublon: bool = False


class ArchivagePayload(BaseModel):
    motif: str = Field(min_length=3, max_length=1000)

    @field_validator("motif", mode="before")
    @classmethod
    def nettoyer(cls, value):
        return value.strip() if isinstance(value, str) else value
