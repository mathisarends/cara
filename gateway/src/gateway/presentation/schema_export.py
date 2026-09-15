import argparse
import json
from pathlib import Path
from typing import Any

import pyrpckit as rpc
from pyrpckit.schema import render_openrpc

from gateway.app import create_app
from gateway.presentation.rpc.contract import gateway_contract

_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_OUTPUT_DIR = _REPO_ROOT / "gateway" / "schema"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the Cara Gateway OpenAPI and OpenRPC contracts"
    )
    parser.add_argument("--output-dir", type=Path, default=_DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    for path in write_gateway_schemas(args.output_dir):
        print(f"Wrote {path}")


def write_gateway_schemas(
    output_dir: Path,
    contract: rpc.RpcContract | None = None,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    return (
        _write_json(output_dir / "openapi.json", create_app().openapi()),
        _write_json(
            output_dir / "gateway.openrpc.json",
            render_openrpc_schema(contract or gateway_contract()),
        ),
    )


def render_openrpc_schema(contract: rpc.RpcContract) -> dict[str, Any]:
    return render_openrpc(
        contract.protocol,
        title=contract.title,
        description=contract.description,
        servers=contract.servers,
    )


def _write_json(path: Path, document: dict[str, Any]) -> Path:
    path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


if __name__ == "__main__":
    main()
