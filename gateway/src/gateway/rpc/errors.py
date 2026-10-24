from fastapi_rpckit import RpcErrorBinding

from gateway.shared import ResourceNotFoundError

RESOURCE_NOT_FOUND = RpcErrorBinding(
    ResourceNotFoundError,
    code="resource_not_found",
    rpc_code=-32004,
    message=lambda error: f"Not found: {error}",
)
