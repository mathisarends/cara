import asyncio

from cara.wakeword import WakeWord, WakeWordListener


async def on_wake_word() -> None:
    print("Wake word detected!")


async def main() -> None:
    listener = WakeWordListener(
        on_detection=on_wake_word,
        wake_word=WakeWord.HEY_MYCROFT,
        sensitivity=0.5,
    )
    await listener.listen()


if __name__ == "__main__":
    asyncio.run(main())
