"""Renders the acknowledgment phrases to WAV clips with the configured voice.

    uv run python scripts/generate_acknowledgment_clips.py

Uses the same Cartesia voice the agent speaks with and writes one clip per
phrase into static/acknowledgments, where PrerenderedAcknowledgment picks them
up.
"""

import argparse
import asyncio
import io
import wave
from collections.abc import Sequence
from pathlib import Path

from dotenv import load_dotenv
from vocalbin.cartesia.tts import AudioEncoding, RawOutputFormat

from voice.acknowledgment import (
    ACKNOWLEDGMENT_CLIPS_DIR,
    GENERIC_ACKNOWLEDGMENTS,
    acknowledgment_clip_name,
)
from voice.tts.cartesia import CartesiaTextToSpeech

# AudioPlayer plays signed 16-bit PCM WAV audio and takes the rate from the
# header, so the clips are rendered in the agent's own playback format. Cartesia's
# own WAV container carries streaming placeholder sizes, so the header is written
# here around the raw PCM instead.
_SAMPLE_RATE = 24_000
_SAMPLE_WIDTH = 2
_CHANNELS = 1


async def main(argv: Sequence[str] | None = None) -> None:
    load_dotenv(override=True)
    args = _parse_args(argv)

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    pending = [
        (phrase, output_dir / acknowledgment_clip_name(phrase))
        for phrase in GENERIC_ACKNOWLEDGMENTS
    ]
    if not args.force:
        pending = [(phrase, path) for phrase, path in pending if not path.exists()]
    if not pending:
        print(f"All clips already rendered in {output_dir}, nothing to do.")
        return

    tts = CartesiaTextToSpeech(
        language=args.language,
        output_format=RawOutputFormat(
            container="raw",
            encoding=AudioEncoding.PCM_S16LE,
            sample_rate=_SAMPLE_RATE,
        ),
    )
    try:
        for phrase, path in pending:
            response = await tts.generate(phrase)
            path.write_bytes(_to_wav(response.audio))
            print(f"wrote  {path.name}  ({phrase})")
    finally:
        await tts.aclose()

    print(f"\n{len(pending)} clips rendered into {output_dir}")


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--language",
        default="en",
        help="ISO-639-1 code the phrases are spoken in.",
    )
    parser.add_argument("--output-dir", type=Path, default=ACKNOWLEDGMENT_CLIPS_DIR)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-render clips that already exist.",
    )
    return parser.parse_args(argv)


def _to_wav(pcm: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(_CHANNELS)
        wav_file.setsampwidth(_SAMPLE_WIDTH)
        wav_file.setframerate(_SAMPLE_RATE)
        wav_file.writeframes(pcm)
    return buffer.getvalue()


if __name__ == "__main__":
    asyncio.run(main())
