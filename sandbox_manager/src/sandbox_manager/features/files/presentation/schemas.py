from pydantic import BaseModel, ConfigDict, Field


class FileEntry(BaseModel):
    path: str
    is_dir: bool
    is_symlink: bool
    size: int | None
    modified: float


class FileMatch(BaseModel):
    path: str
    line_number: int
    line: str
    context_before: tuple[str, ...]
    context_after: tuple[str, ...]


class FileWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str


class FileEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    old: str
    new: str
    replace_all: bool = False


class FileEditResponse(BaseModel):
    count: int


class GrepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pattern: str
    glob: str | None = None
    case_sensitive: bool = True
    context_lines: int = Field(default=0, ge=0, le=10)
    max_matches: int | None = Field(default=None, ge=1)
