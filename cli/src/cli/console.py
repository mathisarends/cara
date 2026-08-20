_RESET = "\x1b[0m"
_DIM = "\x1b[2m"
_CYAN = "\x1b[36m"
_MAGENTA = "\x1b[35m"
_YELLOW = "\x1b[33m"
_RED = "\x1b[31m"
_BLUE = "\x1b[34m"


class Console:
    def __init__(self, color: bool) -> None:
        self._color = color

    def banner(self, url: str) -> None:
        print(self._paint(f"cara · {url}", _MAGENTA))

    def prompt(self) -> str:
        return "\n" + self._paint("you › ", _CYAN)

    def user(self, content: str) -> None:
        print(self._paint("you › ", _CYAN) + content)

    def assistant_prefix(self) -> None:
        print(self._paint("cara › ", _MAGENTA), end="", flush=True)

    def write(self, text: str) -> None:
        print(text, end="", flush=True)

    def newline(self) -> None:
        print()

    def info(self, message: str) -> None:
        print(self._paint(message, _BLUE))

    def tool(self, message: str) -> None:
        print(self._paint(f"  {message}", _DIM))

    def trace(self, message: str) -> None:
        print(self._paint(f"  · {message}", _DIM))

    def warn(self, message: str) -> None:
        print(self._paint(f"  ! {message}", _YELLOW))

    def error(self, message: str) -> None:
        print(self._paint(f"  ✗ {message}", _RED))

    def _paint(self, text: str, code: str) -> str:
        return f"{code}{text}{_RESET}" if self._color else text
