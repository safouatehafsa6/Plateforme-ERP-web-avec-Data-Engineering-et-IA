from pydantic import BaseModel, Field


class RecordingStart(BaseModel):
    mime: str = Field(default="video/webm", max_length=80)
    retention_days: int | None = Field(default=None, ge=1, le=365)


class RecordingConsent(BaseModel):
    decision: str = Field(pattern="^(accepte|refuse)$")
