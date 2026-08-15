from openclaw_client.models import ErrorShape


class OpenClawClientError(Exception):
    pass


class OpenClawProtocolError(OpenClawClientError):
    pass


class OpenClawNotConnectedError(OpenClawClientError):
    pass


class OpenClawGatewayError(OpenClawClientError):
    def __init__(self, error: ErrorShape) -> None:
        super().__init__(f"{error.code}: {error.message}")
        self.error = error

    @property
    def code(self) -> str:
        return self.error.code
