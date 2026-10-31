from pydantic import BaseModel, Field
from typing import Optional


class RoomCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=500)
    is_private: bool = True


class RoomInvite(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class RoomMessage(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class RoomSignal(BaseModel):
    target_user_id: str
    signal_type: str = Field(pattern="^(offer|answer|ice-candidate)$")
    payload: dict
