import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gateway_rpc_client import GatewayRpcClient, RpcConnectionLostError
from gateway_rpc_client.models import RoomState as RpcRoomState
from room.features.room.domain import RoomState
from room.features.room.infrastructure.gateway import GatewayRoomConnection


@pytest.fixture
async def gateway_client() -> Mock:
    report_state = AsyncMock()
    room_api = SimpleNamespace(report_state=report_state)
    gateway_client = Mock(spec=GatewayRpcClient)
    gateway_client.closed = asyncio.get_running_loop().create_future()
    gateway_client.room = room_api
    return gateway_client


@pytest.mark.parametrize("failed", [False, True])
async def test_disconnect_is_observed_before_the_next_heartbeat(
    gateway_client: Mock,
    failed: bool,
) -> None:
    connection = GatewayRoomConnection(gateway_client, heartbeat_seconds=3600)
    waiting = asyncio.create_task(connection.wait_closed())
    await asyncio.sleep(0)
    error = RpcConnectionLostError(sent=False, reason="Gateway disconnected")
    gateway_client.closed.set_result(error if failed else None)

    if failed:
        with pytest.raises(RpcConnectionLostError) as raised:
            await asyncio.wait_for(waiting, timeout=1)
        assert raised.value is error
    else:
        await asyncio.wait_for(waiting, timeout=1)

    gateway_client.room.report_state.assert_not_awaited()


async def test_heartbeat_and_waiter_cancellation_preserve_the_sdk_closure_signal(
    gateway_client: Mock,
) -> None:
    heartbeat_sent = asyncio.Event()

    async def report_state(*, state: RpcRoomState) -> None:
        assert state is RpcRoomState.LISTENING
        heartbeat_sent.set()

    gateway_client.room.report_state.side_effect = report_state
    connection = GatewayRoomConnection(gateway_client, heartbeat_seconds=0.01)
    await connection.report_state(RoomState.LISTENING)
    heartbeat_sent.clear()
    waiting = asyncio.create_task(connection.wait_closed())
    try:
        await asyncio.wait_for(heartbeat_sent.wait(), timeout=1)
        assert not gateway_client.closed.done()
    finally:
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting

    assert not gateway_client.closed.cancelled()
