import argparse
import json
from pathlib import Path
from typing import Any

import pyrpckit as rpc
from pyrpckit.schema import render_openrpc

from gateway.presentation.rpc.contract import gateway_contract

_REPO_ROOT = Path(__file__).resolve().parents[6]
_DEFAULT_OUTPUT_DIR = _REPO_ROOT / "gateway" / "server" / "schema"


def render_openrpc_schema(contract: rpc.RpcContract) -> dict[str, Any]:
    return render_openrpc(
        contract.protocol,
        title=contract.title,
        description=contract.description,
        servers=contract.servers,
    )


def write_gateway_schema(
    output_dir: Path,
    contract: rpc.RpcContract | None = None,
) -> Path:
    selected_contract = contract or gateway_contract()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "gateway.openrpc.json"
    path.write_text(
        json.dumps(
            render_openrpc_schema(selected_contract), indent=2, ensure_ascii=False
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the Cara Gateway OpenRPC contract"
    )
    parser.add_argument("--output-dir", type=Path, default=_DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    print(f"Wrote {write_gateway_schema(args.output_dir)}")


if __name__ == "__main__":
    main()
