import asyncio
import logging

from cara import (
    AnswerGenerated,
    AssistantEvent,
    AssistantLifecycleListener,
    StateChanged,
    Transcribed,
    VoiceAssistant,
)
from cara.wakeword import WakeWord, WakeWordListener
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

logger = logging.getLogger("cara")

load_dotenv(override=True)

class ConsoleLifecycleListener(AssistantLifecycleListener):
    """Example listener: react to each phase of a voice turn.

    Match only the events you care about - this is where you'd drive an LED ring,
    update a UI, play earcons, etc.
    """

    async def on_event(self, event: AssistantEvent) -> None:
        match event:
            case StateChanged(state):
                logger.info("[state] %s", state)
            case Transcribed(transcript):
                logger.info("[heard] %s", transcript)
            case AnswerGenerated(answer):
                logger.info("[answer] %s", answer)
            case _:
                pass


async def main() -> None:
    assistant = VoiceAssistant(
        language="de",
        listeners=[ConsoleLifecycleListener()],
    )

    listener = WakeWordListener(
        on_detection=assistant.run_turn,
        wake_word=WakeWord.HEY_MYCROFT,
        sensitivity=0.5,
    )
    await listener.listen()


if __name__ == "__main__":
    asyncio.run(main())
