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


class LoadSkillParams(ToolParams):
    name: str = Field(description="Name of the skill to load, exactly as listed.")


class BashParams(ToolParams):
    command: str = Field(
        description="Single allow-listed command to execute in the workspace.",
    )


class WeatherParams(ToolParams):
    location: str | None = Field(
        default=None,
        description=(
            "Ort für die Wetterabfrage, z. B. eine Stadt. Ohne Angabe wird der "
            "aktuelle Standort aus dem Kontext verwendet."
        ),
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
