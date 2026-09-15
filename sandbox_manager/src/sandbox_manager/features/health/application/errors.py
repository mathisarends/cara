class DependencyUnavailableError(Exception):
    def __init__(self, dependency: str) -> None:
        super().__init__(f"{dependency} is unavailable")
