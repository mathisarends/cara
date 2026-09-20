from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RoomTopologySettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    display_name: str = Field(min_length=1)


class RoomGroupTopologySettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    display_name: str = Field(min_length=1)
    rooms: tuple[UUID, ...] = Field(min_length=1)
