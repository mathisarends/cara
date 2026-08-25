from pathlib import Path

from gateway_client.codegen import generate


def test_checked_in_client_matches_schema() -> None:
    package_root = Path(__file__).parents[3]

    changed = generate(
        package_root / "gateway" / "server" / "schema" / "gateway.openrpc.json",
        package_root / "gateway" / "client" / "src" / "gateway_client",
        check=True,
    )

    assert not changed
