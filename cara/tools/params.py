from dataclasses import dataclass
from enum import Enum, auto
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from cara.audio.ports import AudioOutput


class AccessMode(Enum):
    READ = auto()
    WRITE = auto()


@dataclass(frozen=True)
class PathField:
    mode: AccessMode


FilePath = Annotated[str, PathField(AccessMode.READ)]
WritablePath = Annotated[str, PathField(AccessMode.WRITE)]


class ToolParams(BaseModel):
    """Base class for tool parameter models."""

    model_config = ConfigDict(extra="forbid")


class EndSessionParams(ToolParams):
    farewell: str = Field(
        description="A short, friendly spoken goodbye in the user's language.",
    )


class SetAudioOutputParams(ToolParams):
    output: AudioOutput = Field(
        description="Configured audio output strategy to activate.",
    )


class SetVolumeParams(ToolParams):
    level: float = Field(
        ge=0.0,
        le=1.0,
        description="Target playback volume, from 0.0 (silent) to 1.0 (full).",
    )


class LoadSkillParams(ToolParams):
    name: str = Field(description="Name of the skill to load, exactly as listed.")


class SetLanguageModelParams(ToolParams):
    name: str = Field(description="Name of the language model profile to activate, exactly as listed.")


class BashParams(ToolParams):
    command: str = Field(
        description="Bash command to execute inside the isolated workspace sandbox.",
    )


class WeatherParams(ToolParams):
    pass


class WebSearchParams(ToolParams):
    query: str = Field(description="Suchanfrage für die Websuche.")
    max_results: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximale Anzahl an Suchergebnissen.",
    )


class ListFilesParams(ToolParams):
    path: FilePath = Field(
        default=".",
        description="Directory to list, relative to the workspace root. Defaults to the root.",
    )


class ReadFileParams(ToolParams):
    path: FilePath = Field(description="Path of the file to read, relative to the workspace root.")


class WriteFileParams(ToolParams):
    path: WritablePath = Field(description="Path of the file to create or overwrite, relative to the workspace root.")
    content: str = Field(description="Full new contents of the file.")


class EditFileParams(ToolParams):
    path: WritablePath = Field(description="Path of the file to edit, relative to the workspace root.")
    old_text: str = Field(description="Exact text to replace. Must occur exactly once in the file.")
    new_text: str = Field(description="Text to insert in place of old_text.")
