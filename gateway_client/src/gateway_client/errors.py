from gateway_client.models import ValidationError


class GatewayError(Exception):
    pass


class GatewayConnectionError(GatewayError):
    pass


class GatewayResponseError(GatewayError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"{status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class GatewayNotFoundError(GatewayResponseError):
    def __init__(self, detail: str) -> None:
        super().__init__(404, detail)


class GatewayValidationError(GatewayResponseError):
    def __init__(self, errors: list[ValidationError]) -> None:
        super().__init__(422, "; ".join(_format(error) for error in errors))
        self.errors = errors


def _format(error: ValidationError) -> str:
    location = ".".join(str(part) for part in error.loc)
    return f"{location}: {error.msg}"
