import re
from pathlib import Path

from voice.acknowledgment.port import AcknowledgmentContext, AcknowledgmentStrategy
from voice.events import AudioPlaybackRequested

# parents[4]: prerendered.py -> acknowledgment/voice/src/voice(project) -> cara
ACKNOWLEDGMENT_CLIPS_DIR = Path(__file__).parents[4] / "static" / "acknowledgments"


class PrerenderedAcknowledgment(AcknowledgmentStrategy):
    """Plays a clip rendered ahead of time by the acknowledgment clip script."""

    def __init__(self, *, clips_dir: Path | None = None) -> None:
        super().__init__()
        self._clips_dir = clips_dir or ACKNOWLEDGMENT_CLIPS_DIR
        self._clips: dict[str, bytes] = {}

    def set_context(self, context: AcknowledgmentContext) -> None:
        super().set_context(context)
        self._clips = {
            path.name: path.read_bytes()
            for path in sorted(self._clips_dir.glob("*.wav"))
        }

    async def acknowledge(self, phrase: str) -> None:
        clip = self._clips.get(acknowledgment_clip_name(phrase))
        if clip is None:
            raise RuntimeError(
                f"No acknowledgment clip for {phrase!r} in {self._clips_dir}. "
                "Run scripts/generate_acknowledgment_clips.py to render it."
            )
        context = self._prepared_context()
        await context.event_bus.request(AudioPlaybackRequested(audio=clip))


def acknowledgment_clip_name(phrase: str) -> str:
    """The clip file a phrase renders to, shared by generator and playback."""
    slug = re.sub(r"[^a-z0-9]+", "-", phrase.lower()).strip("-")
    return f"{slug}.wav"
