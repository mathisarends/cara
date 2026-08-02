from collections.abc import Sequence
from typing import Protocol


class TextTokenizer(Protocol):
    """Minimal tokenizer interface used to measure and slice chunks."""

    def encode(self, text: str) -> Sequence[int]: ...

    def decode(self, tokens: Sequence[int]) -> str: ...


class CharacterTokenizer:
    """Treat each Unicode code point as one token."""

    def encode(self, text: str) -> Sequence[int]:
        return [ord(character) for character in text]

    def decode(self, tokens: Sequence[int]) -> str:
        return "".join(chr(token) for token in tokens)
