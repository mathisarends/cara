import asyncio

from voice.activation import (
    ExternalActivationSource,
    ListenActivation,
    PromptActivation,
)


def test_queues_both_kinds_of_activation_in_order() -> None:
    async def run() -> list[object]:
        source = ExternalActivationSource()
        await source.activate(speech_start_timeout=4.0)
        await source.prompt("The laundry is done")

        activations = source.activations()
        return [await anext(activations), await anext(activations)]

    assert asyncio.run(run()) == [
        ListenActivation(sequence=None, speech_start_timeout=4.0),
        PromptActivation(prompt="The laundry is done"),
    ]
