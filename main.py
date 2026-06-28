import asyncio
import logging

from dotenv import load_dotenv

from cara import (
    AnswerGenerated,
    EventBus,
    HueLifecycleListener,
    SessionEnded,
    SessionStarted,
    SonosAudioPlayer,
    StateChanged,
    Transcribed,
    VoiceAssistant,
)
from cara.wakeword import WakeWord, WakeWordListener

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

logger = logging.getLogger("cara")

load_dotenv(override=True)


class ConsoleLifecycleLogger:
    """Example listener: react to each phase of a voice turn.

    Subscribe only to the events you care about - this is where you'd drive an LED ring,
    update a UI, play earcons, etc.
    """

    def __init__(self, event_bus: EventBus) -> None:
        event_bus.subscribe(StateChanged, self.on_state_changed)
        event_bus.subscribe(SessionStarted, self.on_session_started)
        event_bus.subscribe(SessionEnded, self.on_session_ended)
        event_bus.subscribe(Transcribed, self.on_transcribed)
        event_bus.subscribe(AnswerGenerated, self.on_answer_generated)

    async def on_state_changed(self, event: StateChanged) -> None:
        logger.info("[state] %s", event.state)

    async def on_session_started(self, event: SessionStarted) -> None:
        logger.info("[session] started")

    async def on_session_ended(self, event: SessionEnded) -> None:
        logger.info("[session] ended")

    async def on_transcribed(self, event: Transcribed) -> None:
        logger.info("[heard] %s", event.transcript)

    async def on_answer_generated(self, event: AnswerGenerated) -> None:
        logger.info("[answer] %s", event.answer)


async def main() -> None:
    # Drive the Hue room "Zimmer 1" in sync with the assistant lifecycle.
    # Needs HUE_BRIDGE_IP and HUE_APP_KEY in the environment / .env.
    events = EventBus()
    ConsoleLifecycleLogger(events)

    hue = HueLifecycleListener(events, room_name="Mein Zimmer")
    await hue.start()

    # Set speaker_name to target a specific speaker, e.g. SonosAudioPlayer(speaker_name="Wohnzimmer").
    # Without a name the first discovered Sonos on the network is used.
    assistant = VoiceAssistant(
        language="de",
        event_bus=events,
        player=SonosAudioPlayer(),
    )

    listener = WakeWordListener(
        on_detection=assistant.run_session,
        wake_word=WakeWord.HEY_MYCROFT,
        sensitivity=0.5,
    )
    try:
        await listener.listen()
    finally:
        await hue.aclose()


if __name__ == "__main__":
    asyncio.run(main())
