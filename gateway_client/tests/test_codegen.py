from pathlib import Path

from gateway_client.codegen import generate


def test_checked_in_client_matches_schema() -> None:
    package_root = Path(__file__).parents[2]

    changed = generate(
        package_root / "gateway" / "schema" / "gateway.openrpc.json",
        package_root / "gateway_client" / "src" / "gateway_client",
        check=True,
    )

    assert not changed
