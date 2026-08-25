import argparse
import json
from pathlib import Path
from typing import Any

from pyrpckit import RpcProtocol
from pyrpckit.schema import render_json_schema, render_openrpc

from gateway.features import gateway_protocol

_REPO_ROOT = Path(__file__).resolve().parents[5]
_DEFAULT_OUTPUT_DIR = _REPO_ROOT / "gateway" / "schema"


def render_gateway_schema(protocol: RpcProtocol) -> dict[str, Any]:
    return render_json_schema(
        protocol,
        title="Cara Gateway Protocol",
        description="JSON-RPC requests, responses, and notifications.",
        schema_id="https://cara.local/gateway.schema.json",
    )


def render_openrpc_schema(protocol: RpcProtocol) -> dict[str, Any]:
    return render_openrpc(
        protocol,
        title="Cara Gateway",
        description="Typed JSON-RPC API over the Cara Gateway WebSocket.",
        servers=({"name": "local", "url": "ws://127.0.0.1:8000/v1/gateway"},),
    )


def write_gateway_schemas(
    output_dir: Path,
    protocol: RpcProtocol | None = None,
) -> tuple[Path, Path]:
    selected_protocol = protocol or gateway_protocol()
    output_dir.mkdir(parents=True, exist_ok=True)
    gateway_schema_path = output_dir / "gateway.schema.json"
    openrpc_schema_path = output_dir / "gateway.openrpc.json"
    _write_json(gateway_schema_path, render_gateway_schema(selected_protocol))
    _write_json(openrpc_schema_path, render_openrpc_schema(selected_protocol))
    return gateway_schema_path, openrpc_schema_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the Cara Gateway JSON Schema and OpenRPC contract."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {_DEFAULT_OUTPUT_DIR})",
    )
    args = parser.parse_args()
    for path in write_gateway_schemas(args.output_dir):
        print(f"Wrote {path}")


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
