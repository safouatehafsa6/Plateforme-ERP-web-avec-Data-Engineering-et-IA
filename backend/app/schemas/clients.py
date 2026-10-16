import re

from pydantic import BaseModel, Field, field_validator


_EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}$"
)
_PHONE_PATTERN = re.compile(r"^\+?[0-9\s()./-]+$")


class ClientPayload(BaseModel):
    """Payload partagé par la création et la modification d’un client."""

    nom: str = Field(min_length=1, max_length=150)
    email: str | None = Field(default=None, max_length=150)
    telephone: str | None = Field(default=None, max_length=30)
    adresse: str | None = Field(default=None, max_length=1000)

    @field_validator("nom", mode="before")
    @classmethod
    def nettoyer_nom(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("email", "telephone", "adresse", mode="before")
    @classmethod
    def normaliser_champs_optionnels(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("email")
    @classmethod
    def valider_email(cls, value):
        if value is not None and not _EMAIL_PATTERN.fullmatch(value):
            raise ValueError("Saisissez une adresse e-mail valide.")
        return value

    @field_validator("telephone")
    @classmethod
    def valider_telephone(cls, value):
        if value is None:
            return None
        if not _PHONE_PATTERN.fullmatch(value):
            raise ValueError("Le téléphone contient des caractères non autorisés.")
        nombre_chiffres = sum(character.isdigit() for character in value)
        if not 7 <= nombre_chiffres <= 15:
            raise ValueError("Le téléphone doit contenir entre 7 et 15 chiffres.")
        return value
