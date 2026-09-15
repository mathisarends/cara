import argparse
import json
from pathlib import Path

from sandbox_manager.app import create_app
from sandbox_manager.settings import SandboxManagerSettings

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUTPUT_DIR = _PACKAGE_ROOT / "schema"


def write_schema(output_dir: Path) -> Path:
    settings = SandboxManagerSettings.model_validate({"token": "schema-export"})
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "openapi.json"
    path.write_text(
        json.dumps(create_app(settings).openapi(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the Cara Sandbox Manager OpenAPI schema"
    )
    parser.add_argument("--output-dir", type=Path, default=_DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    print(f"Wrote {write_schema(args.output_dir)}")


if __name__ == "__main__":
    main()
