from uuid import UUID, uuid4

from fastapi import WebSocket, WebSocketDisconnect

from gateway.features.conversation.application import EventBroker, EventReceiver
from gateway.features.conversation.presentation.schemas import event_message


async def serve_socket(
    websocket: WebSocket,
    session_id: UUID,
    broker: EventBroker,
) -> None:
    client_id = str(uuid4())
    receiver = broker.connect(client_id)
    broker.subscribe(client_id, session_id)
    await websocket.accept()
    try:
        await _send_events(websocket, receiver)
    except WebSocketDisconnect:
        pass
    finally:
        broker.disconnect(client_id)


async def _send_events(websocket: WebSocket, receiver: EventReceiver) -> None:
    while True:
        event = await receiver.receive()
        envelope = event_message(event)
        await websocket.send_json(envelope.model_dump(mode="json", exclude_none=True))
