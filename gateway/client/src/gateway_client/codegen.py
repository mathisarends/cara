import argparse
import json
import subprocess
from pathlib import Path

from pyrpckit.codegen import render_python_client
from pyrpckit.codegen.python import PythonClientOptions
from pyrpckit.codegen.writer import write_files

_DEFAULT_OUTPUT = Path("gateway/client/src/gateway_client")


def generate(schema_path: Path, output_directory: Path, *, check: bool = False) -> bool:
    """Render the client from an OpenRPC document, keeping __init__.py hand-written."""
    document = json.loads(schema_path.read_text(encoding="utf-8"))
    options = PythonClientOptions(
        package="gateway_client",
        client_name="GatewayClient",
        source=schema_path.name,
    )
    files = render_python_client(document, options)
    generated = {
        path: _ruff_format(path, content)
        for path, content in files.items()
        if path != "__init__.py"
    }
    changed = write_files(output_directory, generated, check=check)
    return bool(changed)


def _ruff_format(filename: str, content: str) -> str:
    """Apply the repo's ruff import sorting and formatting to generated code."""
    sorted_content = subprocess.run(
        ["ruff", "check", "--fix-only", "--stdin-filename", filename, "-"],
        input=content,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return subprocess.run(
        ["ruff", "format", "--stdin-filename", filename, "-"],
        input=sorted_content,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the typed Gateway client")
    parser.add_argument("schema", type=Path)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    changed = generate(arguments.schema, arguments.output, check=arguments.check)
    if arguments.check and changed:
        parser.error("generated client is out of date")


if __name__ == "__main__":
    main()
