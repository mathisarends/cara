from pydantic import BaseModel, ConfigDict, Field

from cara.audio.ports import AudioOutput


class ToolParams(BaseModel):
    """Base class for tool parameter models."""

    model_config = ConfigDict(extra="forbid")


class SetAudioOutputParams(ToolParams):
    output: AudioOutput = Field(
        description="Configured audio sink to activate.",
    )


class SetVolumeParams(ToolParams):
    level: float = Field(
        ge=0.0,
        le=1.0,
        description="Target playback volume, from 0.0 (silent) to 1.0 (full).",
    )


class LoadSkillParams(ToolParams):
    name: str = Field(description="Name of the skill to load, exactly as listed.")


class BashParams(ToolParams):
    command: str = Field(
        description="Bash command to execute inside the isolated workspace sandbox.",
    )


class WeatherParams(ToolParams):
    location: str | None = Field(
        default=None,
        description=(
            "City or place to look up the weather for, e.g. 'München'. Omit this to use the user's current location."
        ),
    )


class WebSearchParams(ToolParams):
    query: str = Field(description="Suchanfrage für die Websuche.")
    max_results: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximale Anzahl an Suchergebnissen.",
    )


class SearchMemoryParams(ToolParams):
    query: str = Field(description="Question or search phrase to look up in long-term memory.")
    limit: int = Field(default=5, ge=1, le=20, description="Maximum number of results.")
    vector_weight: float = Field(default=0.7, ge=0.0, description="Weight for semantic similarity.")
    text_weight: float = Field(default=0.3, ge=0.0, description="Weight for exact keyword matching.")


class ListFilesParams(ToolParams):
    path: str = Field(
        default=".",
        description="Directory to list, relative to the workspace root. Defaults to the root.",
    )


class GlobParams(ToolParams):
    pattern: str = Field(description="Glob pattern relative to the workspace root, for example '**/*.py'.")
    max_results: int = Field(
        default=200,
        ge=1,
        le=1_000,
        description="Maximum number of matching paths to return.",
    )


class GrepParams(ToolParams):
    pattern: str = Field(description="Regular expression to search for in workspace files.")
    glob: str | None = Field(default=None, description="Optional glob restricting which files are searched.")
    case_sensitive: bool = Field(default=True, description="Whether matching is case-sensitive.")
    context_lines: int = Field(
        default=0,
        ge=0,
        le=10,
        description="Number of surrounding lines to include before and after each match.",
    )
    max_matches: int = Field(
        default=100,
        ge=1,
        le=1_000,
        description="Maximum number of matches to return.",
    )


class ReadFileParams(ToolParams):
    path: str = Field(description="Path of the file to read, relative to the workspace root.")


class WriteFileParams(ToolParams):
    path: str = Field(description="Path of the file to create or overwrite, relative to the workspace root.")
    content: str = Field(description="Full new contents of the file.")


class EditFileParams(ToolParams):
    path: str = Field(description="Path of the file to edit, relative to the workspace root.")
    old_text: str = Field(description="Exact text to replace. Must occur exactly once in the file.")
    new_text: str = Field(description="Text to insert in place of old_text.")
