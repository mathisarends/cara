import asyncio
import logging

from room.features.health.application import ReadinessService
from room.features.room.application.ports import RoomConnection, RoomConnector
from room.features.room.application.registration import RegistrationService
from room.features.room.application.reporting import ReportingService
from room.features.room.domain import Room

logger = logging.getLogger(__name__)


class GatewayLink:
    def __init__(
        self,
        room: Room,
        registration_service: RegistrationService,
        room_connector: RoomConnector,
        reporting_service: ReportingService,
        readiness_service: ReadinessService,
        *,
        initial_retry_seconds: float = 1.0,
        maximum_retry_seconds: float = 30.0,
    ) -> None:
        self._room = room
        self._registration_service = registration_service
        self._room_connector = room_connector
        self._reporting_service = reporting_service
        self._readiness_service = readiness_service
        self._initial_retry_seconds = initial_retry_seconds
        self._maximum_retry_seconds = maximum_retry_seconds
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        delay = self._initial_retry_seconds
        while not self._stopped.is_set():
            room_connection: RoomConnection | None = None
            try:
                await self._registration_service.register()
                room_connection = await self._room_connector.connect()
                await self._reporting_service.attach(room_connection)
                self._readiness_service.gateway_connected(True)
                delay = self._initial_retry_seconds
                logger.info("Room %s connected to the Gateway", self._room.room_id)
                await self._wait_until_disconnected(room_connection)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Room Gateway link failed; reconnecting")
            finally:
                self._readiness_service.gateway_connected(False)
                if room_connection is not None:
                    await self._reporting_service.detach(room_connection)
                    await room_connection.close()
            if await self._wait_for_retry(delay):
                return
            delay = min(delay * 2, self._maximum_retry_seconds)

    def stop(self) -> None:
        self._stopped.set()

    async def _wait_for_retry(self, delay: float) -> bool:
        try:
            await asyncio.wait_for(self._stopped.wait(), timeout=delay)
        except TimeoutError:
            return False
        return True

    async def _wait_until_disconnected(
        self,
        room_connection: RoomConnection,
    ) -> None:
        connection_closed = asyncio.create_task(room_connection.wait_closed())
        stop_requested = asyncio.create_task(self._stopped.wait())
        done, pending = await asyncio.wait(
            (connection_closed, stop_requested),
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        if connection_closed in done:
            await connection_closed
