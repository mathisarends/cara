import asyncio

import lameenc

from gateway.features.voice.application import AudioEncoder


class LameMp3Encoder(AudioEncoder):
    def __init__(self, output_sample_rate: int, bit_rate_kbps: int) -> None:
        self._output_sample_rate = output_sample_rate
        self._bit_rate_kbps = bit_rate_kbps

    async def encode(self, pcm: bytes, sample_rate: int) -> bytes:
        return await asyncio.to_thread(self._encode, pcm, sample_rate)

    def _encode(self, pcm: bytes, sample_rate: int) -> bytes:
        encoder = lameenc.Encoder()
        encoder.set_channels(1)
        encoder.set_in_sample_rate(sample_rate)
        # One output rate keeps segments from different inputs concatenable.
        encoder.set_out_sample_rate(self._output_sample_rate)
        encoder.set_bit_rate(self._bit_rate_kbps)
        encoder.set_quality(2)
        return bytes(encoder.encode(pcm) + encoder.flush())
