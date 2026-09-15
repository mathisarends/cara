class InvalidWorkspaceIdError(Exception):
    def __init__(self, workspace_id: str) -> None:
        super().__init__(
            f"workspace id {workspace_id!r} contains unsupported characters"
        )


class StdinNotSupportedError(Exception):
    def __init__(self) -> None:
        super().__init__("stdin is not supported by the sandbox runtime")
