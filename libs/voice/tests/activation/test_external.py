import asyncio

from voice.activation import (
    ExternalActivationSource,
    ListenActivation,
)


def test_queues_manual_activation() -> None:
    async def run() -> ListenActivation:
        source = ExternalActivationSource()
        await source.activate(speech_start_timeout=4.0)

        activations = source.activations()
        return await anext(activations)

    assert asyncio.run(run()) == ListenActivation(
        sequence=None,
        speech_start_timeout=4.0,
    )
