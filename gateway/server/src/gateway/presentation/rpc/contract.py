import pyrpckit as rpc

from gateway.presentation.rpc.channels import gateway_channel


def gateway_contract(channel: rpc.RpcChannel | None = None) -> rpc.RpcContract:
    return rpc.RpcContract.from_channels(
        channels=(channel or gateway_channel(),),
        title="Cara Gateway",
        description="Typed JSON-RPC API over the Cara Gateway WebSocket.",
        server_urls={"local": "ws://127.0.0.1:8000/v1/gateway"},
    )
