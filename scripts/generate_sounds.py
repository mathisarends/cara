"""Generate Cara's earcon set via the ElevenLabs sound generation package.

Run with: `uv run python scripts/generate_sounds.py`

Sounds share a clean, airy, premium character (think Wispr Flow): soft
bell-like tones, gentle envelopes, minimal reverb, no music or noise. Files
are written to the top-level `sounds/` directory as 44.1 kHz / 128 kbps MP3.
"""

import argparse
import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from sound_generation import ElevenLabsSoundGenerator, SoundEffectFormat, SoundEffectRequest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("generate_sounds")

_SOUNDS_DIR = Path(__file__).resolve().parent.parent / "sounds"

_SHARED_CHARACTER = (
    "Premium voice-assistant earcon, Alexa-style but warmer. Rounded glassy marimba tone with body "
    "and a soft felt-mallet attack, warm LOW-MID register, never thin or high-pitched. Smooth decay, "
    "short tasteful reverb, no harshness. Studio-grade, expensive."
)


@dataclass(frozen=True)
class Earcon:
    name: str
    description: str
    duration_seconds: float


_EARCONS = [
    Earcon(
        name="wake",
        description="Two rounded low-mid notes stepping UP with a confident PUNCHY attack and a deep "
        "low thump under the first, warm and welcoming, second note brighter. Impactful, never squeaky.",
        duration_seconds=1.3,
    ),
    Earcon(
        name="interrupt",
        description="One dark soft muted low thud, felt mallet on a deep wooden bar; quick, dry, "
        "percussive, almost no tail. The lowest and shortest sound in the set.",
        duration_seconds=0.6,
    ),
    Earcon(
        name="listening",
        description="One warm mid note with a gentle shimmering swell that rises then settles, "
        "breathing and inviting. Single note only, airy but full.",
        duration_seconds=0.9,
    ),
    Earcon(
        name="success",
        description="Bright rewarding confirmation: three warm notes climbing a clear major interval "
        "and resolving on a satisfying 'ta-da', glowing and cheerful. Uplifting task-complete chime.",
        duration_seconds=1.3,
    ),
    Earcon(
        name="error",
        description="Clear negative 'failed' signal: two low notes buzzing DOWNWARD (a soft "
        "'bwoop-bwoop'), muted and slightly dissonant, obviously saying no. Non-alarming but "
        "unmistakably an error.",
        duration_seconds=1.0,
    ),
    Earcon(
        name="sleep",
        description="One long deep note softly descending and fading into silence like a warm "
        "exhale, mellow pad-like tail. The most sustained, lowest-drifting sound in the set.",
        duration_seconds=1.6,
    ),
]


async def _generate(generator: ElevenLabsSoundGenerator, earcon: Earcon, suffix: str = "") -> None:
    request = SoundEffectRequest(
        text=f"{_SHARED_CHARACTER} {earcon.description}",
        output_format=SoundEffectFormat.MP3_44100_128,
        duration_seconds=earcon.duration_seconds,
        prompt_influence=0.7,
    )
    response = await generator.generate(request)
    destination = _SOUNDS_DIR / f"{earcon.name}{suffix}.mp3"
    destination.write_bytes(response.audio)
    logger.info("Wrote %s (%d bytes).", destination, len(response.audio))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Cara's earcon set.")
    parser.add_argument(
        "names",
        nargs="*",
        help="Earcon names to generate (default: all). E.g. `wake error success`.",
    )
    parser.add_argument(
        "--variants",
        type=int,
        default=1,
        help="Takes per earcon. >1 writes suffixed files (wake_a, wake_b, ...) to compare.",
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    load_dotenv(override=True)
    _SOUNDS_DIR.mkdir(exist_ok=True)

    selected = _EARCONS if not args.names else [e for e in _EARCONS if e.name in args.names]
    if args.names and (unknown := set(args.names) - {e.name for e in selected}):
        raise SystemExit(f"Unknown earcon name(s): {', '.join(sorted(unknown))}")

    generator = ElevenLabsSoundGenerator()
    for earcon in selected:
        if args.variants <= 1:
            await _generate(generator, earcon)
        else:
            for index in range(args.variants):
                await _generate(generator, earcon, suffix=f"_{chr(ord('a') + index)}")


if __name__ == "__main__":
    asyncio.run(main())
