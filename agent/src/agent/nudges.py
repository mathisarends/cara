import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import replace

from llm import ToolResultMessage

_FAILURE_THRESHOLD = 2
_SILENCE_THRESHOLD_SECONDS = 20.0


class ProgressNudges:
    """Notices what the model does not reliably track itself during one turn,
    repeated tool failures and long silence, and asks it to update the user."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._failures: Counter[str] = Counter()
        self._reported_failures: set[str] = set()
        self._last_update = clock()

    def record_update(self) -> None:
        self._last_update = self._clock()

    def annotate(self, results: Sequence[ToolResultMessage]) -> list[ToolResultMessage]:
        annotated = list(results)
        notes = self._failure_notes(results)
        if silence := self._silence_note():
            notes.append(silence)
        if notes and annotated:
            last = annotated[-1]
            note = " ".join(notes)
            annotated[-1] = replace(
                last, content=f"{last.content}\n\n[Runtime note] {note}"
            )
        return annotated

    def _failure_notes(self, results: Sequence[ToolResultMessage]) -> list[str]:
        self._failures.update(result.tool_name for result in results if result.is_error)
        notes: list[str] = []
        for name, count in self._failures.items():
            if count < _FAILURE_THRESHOLD or name in self._reported_failures:
                continue
            self._reported_failures.add(name)
            notes.append(
                f"`{name}` has failed {count} times in this turn. Before retrying, "
                "briefly tell the user what isn't working and what you'll try "
                "next, or ask them how to proceed."
            )
        return notes

    def _silence_note(self) -> str | None:
        now = self._clock()
        silent_for = now - self._last_update
        if silent_for < _SILENCE_THRESHOLD_SECONDS:
            return None
        self._last_update = now
        return (
            f"You have been working for {silent_for:.0f} seconds without telling "
            "the user anything. Briefly tell them where you stand before continuing."
        )
