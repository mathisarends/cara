import re
import shutil
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass

_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_DIM = "\x1b[2m"
_CYAN = "\x1b[36m"
_MAGENTA = "\x1b[35m"
_YELLOW = "\x1b[33m"
_RED = "\x1b[31m"
_BLUE = "\x1b[34m"

_CURSOR_UP = "\x1b[A"
_ERASE_BELOW = "\x1b[J"

_PROMPT = "you › "
_ELLIPSIS = "…"
_ANSI = re.compile(r"\x1b\[[0-9;]*m")

_LABEL_WIDTH = 9
_INDENT = "  "
_RESULT_INDENT = "    "


@dataclass(frozen=True, slots=True)
class Suggestion:
    value: str
    """What the input line becomes when this suggestion is accepted."""
    label: str
    detail: str


type Completer = Callable[[str], Sequence[Suggestion]]


def _no_suggestions(text: str) -> Sequence[Suggestion]:
    return ()


class Console:
    """Owns stdout: gateway output is printed above a live prompt line.

    Interactive mode keeps the prompt as the last row of the screen and
    redraws it whenever output arrives, so typing survives a streaming turn.
    Completions for the half-typed line sit in that same live region, just
    above the prompt. Without a terminal the live region is dropped and
    output is plain.
    """

    def __init__(
        self,
        color: bool,
        interactive: bool,
        completer: Completer = _no_suggestions,
    ) -> None:
        self._color = color
        self._interactive = interactive
        self._completer = completer
        self._input = ""
        self._hint = ""
        self._partial = ""
        self._rows = 0
        self._menu: tuple[Suggestion, ...] = ()
        self._chosen: int | None = None

    @property
    def input(self) -> str:
        return self._input

    def type(self, text: str) -> None:
        self._input += text
        self._close_menu()
        self._refresh()

    def backspace(self) -> None:
        self._input = self._input[:-1]
        self._close_menu()
        self._refresh()

    def complete(self) -> None:
        """Write the next matching suggestion into the input line.

        The first tab freezes the matches for what is typed so far; further
        tabs walk that same list instead of recomputing it against the line
        they just rewrote.
        """
        if self._chosen is None:
            self._menu = tuple(self._completer(self._input))
            if not self._menu:
                return
            self._chosen = 0
        else:
            self._chosen = (self._chosen + 1) % len(self._menu)
        self._input = self._menu[self._chosen].value
        self._refresh()

    def take_input(self) -> str:
        text, self._input = self._input, ""
        self._close_menu()
        self._refresh()
        return text

    def set_hint(self, hint: str) -> None:
        self._hint = hint
        self._refresh()

    def close(self) -> None:
        self._erase()
        if self._partial:
            self._out("\n")
            self._partial = ""

    def header(self, subtitle: str) -> None:
        self._line(
            self._paint("cara", _MAGENTA + _BOLD) + self._paint(f"  {subtitle}", _DIM)
        )

    def field(self, label: str, value: str) -> None:
        self._line(self._paint(f"{_INDENT}{label:<{_LABEL_WIDTH}}", _DIM) + value)

    def user(self, content: str) -> None:
        self._line(self._paint(_PROMPT, _CYAN) + content)

    def assistant_prefix(self) -> None:
        self.write(self._paint("cara › ", _MAGENTA))

    def newline(self) -> None:
        self.write("\n")

    def blank(self) -> None:
        """One empty row, to set a block apart from what follows."""
        self._line("")

    def info(self, message: str) -> None:
        self._line(self._paint(message, _BLUE))

    def tool_call(self, name: str, detail: str) -> None:
        """The headline of one tool call: what ran, and on what."""
        line = self._paint(f"{_INDENT}● ", _CYAN) + self._paint(name, _CYAN)
        if detail:
            line += self._paint(f"  {detail}", _DIM)
        self._line(line)

    def tool_result(self, lines: Sequence[str], failed: bool) -> None:
        """What the call above returned, indented under its headline."""
        if not lines:
            return
        marker, style = ("✗", _RED) if failed else ("↳", _DIM)
        head, *rest = lines
        body = [f"{_RESULT_INDENT}{marker} {head}"]
        body += [f"{_RESULT_INDENT}  {line}" for line in rest]
        self._line(self._paint("\n".join(body), style))

    def trace(self, message: str) -> None:
        self._line(self._paint(f"{_INDENT}· {message}", _DIM))

    def warn(self, message: str) -> None:
        self._line(self._paint(f"{_INDENT}! {message}", _YELLOW))

    def error(self, message: str) -> None:
        self._line(self._paint(f"{_INDENT}✗ {message}", _RED))

    def write(self, text: str) -> None:
        if not text:
            return
        self._erase()
        completed, separator, partial = (self._partial + text).rpartition("\n")
        self._partial = partial
        if not self._interactive:
            self._out(text)
        elif separator:
            self._out(completed + "\n")
        self._render()

    def _line(self, text: str) -> None:
        self.write(f"\n{text}\n" if self._partial else f"{text}\n")

    def _close_menu(self) -> None:
        self._menu = ()
        self._chosen = None

    def _refresh(self) -> None:
        self._erase()
        self._render()

    def _erase(self) -> None:
        if self._rows == 0:
            return
        self._out("\r" + _CURSOR_UP * (self._rows - 1) + _ERASE_BELOW)
        self._rows = 0

    def _render(self) -> None:
        if not self._interactive:
            return
        rows = [_fit_tail(self._partial, _width() - 1)] if self._partial else []
        rows.extend(self._hint_rows())
        rows.extend(self._menu_rows())
        rows.append(self._prompt_row())
        self._out("\n".join(rows))
        self._rows = len(rows)

    def _hint_rows(self) -> list[str]:
        """The hint sits above the prompt, never in it.

        Written into the input line it reads like text already typed, which
        is exactly what the one line the user owns must never do.
        """
        if self._input or not self._hint:
            return []
        return [self._paint(_fit_head(f"{_INDENT}{self._hint}", _width() - 1), _DIM)]

    def _menu_rows(self) -> list[str]:
        """The suggestions for what is typed, one per row above the prompt."""
        suggestions = (
            self._menu if self._chosen is not None else self._completer(self._input)
        )
        if not suggestions:
            return []
        width = max(len(suggestion.label) for suggestion in suggestions)
        room = _width() - 1
        return [
            _fit_head(self._menu_row(index, suggestion, width), room)
            for index, suggestion in enumerate(suggestions)
        ]

    def _menu_row(self, index: int, suggestion: Suggestion, width: int) -> str:
        picked = index == self._chosen
        marker = self._paint(f"{_INDENT}› ", _CYAN) if picked else f"{_INDENT}  "
        label = f"{suggestion.label:<{width}}"
        return (
            marker
            + (self._paint(label, _CYAN) if picked else label)
            + self._paint(f"  {suggestion.detail}", _DIM)
        )

    def _prompt_row(self) -> str:
        room = _width() - len(_PROMPT) - 1
        return self._paint(_PROMPT, _CYAN) + _fit_tail(self._input, room)

    def _paint(self, text: str, code: str) -> str:
        return f"{code}{text}{_RESET}" if self._color else text

    def _out(self, text: str) -> None:
        sys.stdout.write(text)
        sys.stdout.flush()


def _fit_tail(text: str, room: int) -> str:
    """Keep the end of a row so it never wraps; colour is dropped when it is cut."""
    plain = _ANSI.sub("", text)
    if len(plain) <= room:
        return text
    if room <= 1:
        return ""
    return _ELLIPSIS + plain[-(room - 1) :]


def _fit_head(text: str, room: int) -> str:
    """Keep the start of a row - what a suggestion is matters more than its tail."""
    plain = _ANSI.sub("", text)
    if len(plain) <= room:
        return text
    if room <= 1:
        return ""
    return plain[: room - 1] + _ELLIPSIS


def _width() -> int:
    return shutil.get_terminal_size(fallback=(80, 24)).columns
