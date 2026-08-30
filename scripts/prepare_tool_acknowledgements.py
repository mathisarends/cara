import argparse
import asyncio
import io
import wave
from pathlib import Path

from vocalbin.deepgram.tts import (
    AudioEncoding,
    TextToSpeech,
    TextToSpeechModel,
)

from voice.handler.tool_acknowledgement import TOOL_ACKNOWLEDGEMENTS

_PROJECT_ROOT = Path(__file__).parents[1]
_DEFAULT_OUTPUT_DIR = _PROJECT_ROOT / "voice" / "static" / "acknowledgements"
_DEFAULT_SAMPLE_RATE = 24_000
_DEFAULT_VOICE = TextToSpeechModel.AURA_2_ATHENA_EN


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pre-synthesize static WAV clips for tool acknowledgements."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_DEFAULT_OUTPUT_DIR,
        help=f"Destination directory (default: {_DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--voice",
        default=_DEFAULT_VOICE,
        help=f"Deepgram model name (default: {_DEFAULT_VOICE})",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=_DEFAULT_SAMPLE_RATE,
        help=f"WAV sample rate (default: {_DEFAULT_SAMPLE_RATE})",
    )
    return parser.parse_args()


async def _prepare(
    output_dir: Path,
    *,
    voice: str,
    sample_rate: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    async with TextToSpeech(
        model=voice,
        encoding=AudioEncoding.LINEAR16,
        sample_rate=sample_rate,
    ) as text_to_speech:
        for name, phrase in TOOL_ACKNOWLEDGEMENTS:
            response = await text_to_speech.generate(phrase)
            destination = output_dir / f"{name}.wav"
            destination.write_bytes(_to_wav(response.audio, sample_rate=sample_rate))
            print(f"Prepared {destination}: {phrase}")


def _to_wav(pcm: bytes, *, sample_rate: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return output.getvalue()


def main() -> None:
    args = _parse_args()
    if args.sample_rate <= 0:
        raise ValueError("sample-rate must be positive")
    asyncio.run(
        _prepare(
            args.output_dir,
            voice=args.voice,
            sample_rate=args.sample_rate,
        )
    )


if __name__ == "__main__":
    main()
