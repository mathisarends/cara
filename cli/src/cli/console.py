import re
import shutil
import sys

_RESET = "\x1b[0m"
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


class Console:
    """Owns stdout: gateway output is printed above a live prompt line.

    Interactive mode keeps the prompt as the last row of the screen and
    redraws it whenever output arrives, so typing survives a streaming turn.
    Without a terminal the prompt line is dropped and output is plain.
    """

    def __init__(self, color: bool, interactive: bool) -> None:
        self._color = color
        self._interactive = interactive
        self._input = ""
        self._hint = ""
        self._partial = ""
        self._rows = 0

    @property
    def input(self) -> str:
        return self._input

    def type(self, text: str) -> None:
        self._input += text
        self._refresh()

    def backspace(self) -> None:
        self._input = self._input[:-1]
        self._refresh()

    def take_input(self) -> str:
        text, self._input = self._input, ""
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

    def banner(self, url: str) -> None:
        self._line(self._paint(f"cara · {url}", _MAGENTA))

    def user(self, content: str) -> None:
        self._line(self._paint(_PROMPT, _CYAN) + content)

    def assistant_prefix(self) -> None:
        self.write(self._paint("cara › ", _MAGENTA))

    def newline(self) -> None:
        self.write("\n")

    def info(self, message: str) -> None:
        self._line(self._paint(message, _BLUE))

    def tool(self, message: str) -> None:
        self._line(self._paint(f"  {message}", _DIM))

    def trace(self, message: str) -> None:
        self._line(self._paint(f"  · {message}", _DIM))

    def warn(self, message: str) -> None:
        self._line(self._paint(f"  ! {message}", _YELLOW))

    def error(self, message: str) -> None:
        self._line(self._paint(f"  ✗ {message}", _RED))

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
        rows.append(self._prompt_row())
        self._out("\n".join(rows))
        self._rows = len(rows)

    def _prompt_row(self) -> str:
        room = _width() - len(_PROMPT) - 1
        if self._input:
            return self._paint(_PROMPT, _CYAN) + _fit_tail(self._input, room)
        return self._paint(_PROMPT, _CYAN) + self._paint(
            _fit_tail(self._hint, room), _DIM
        )

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


def _width() -> int:
    return shutil.get_terminal_size(fallback=(80, 24)).columns
