class WorkspaceFileNotFoundError(Exception):
    def __init__(self, path: str) -> None:
        super().__init__(f"file {path!r} does not exist")


class WorkspaceNotADirectoryError(Exception):
    def __init__(self, path: str) -> None:
        super().__init__(f"{path!r} is not a directory")


class PathOutsideWorkspaceError(Exception):
    def __init__(self, path: str) -> None:
        super().__init__(f"{path!r} is outside the workspace")


class InvalidEditError(Exception):
    pass
