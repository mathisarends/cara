from typing import Annotated, Literal

from pydantic import BaseModel, Field


class Word(BaseModel):
    word: str
    confidence: float


class Connected(BaseModel):
    type: Literal["connected"] = "connected"
    request_id: str


class TurnStart(BaseModel):
    type: Literal["turn.start"] = "turn.start"
    request_id: str
    turn_index: int
    transcript: str
    words: list[Word] = Field(default_factory=list)
    end_of_turn_confidence: float


class TurnUpdate(BaseModel):
    type: Literal["turn.update"] = "turn.update"
    request_id: str
    turn_index: int
    transcript: str
    words: list[Word] = Field(default_factory=list)
    end_of_turn_confidence: float


class TurnEagerEnd(BaseModel):
    type: Literal["turn.eager_end"] = "turn.eager_end"
    request_id: str
    turn_index: int
    transcript: str
    words: list[Word] = Field(default_factory=list)
    end_of_turn_confidence: float


class TurnResume(BaseModel):
    type: Literal["turn.resume"] = "turn.resume"
    request_id: str
    turn_index: int
    transcript: str
    words: list[Word] = Field(default_factory=list)
    end_of_turn_confidence: float


class TurnEnd(BaseModel):
    type: Literal["turn.end"] = "turn.end"
    request_id: str
    turn_index: int
    transcript: str
    words: list[Word] = Field(default_factory=list)
    end_of_turn_confidence: float


type TurnEvent = TurnStart | TurnUpdate | TurnEagerEnd | TurnResume | TurnEnd

type Event = Annotated[
    Connected | TurnEvent,
    Field(discriminator="type"),
]
