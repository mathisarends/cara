# gateway-codegen

Generates the complete `gateway_client` package from the Gateway's OpenRPC
contract using `pyrpckit.codegen` 0.4.0. The bundled generator owns the typed
models, namespace methods, runtime, and WebSocket transport. This package adds
the bearer-token `connect_gateway` helper and checks generated output for drift.

```bash
uv run --package gateway-server cara-gateway-schema
uv run --package gateway-codegen cara-gateway-client-generate \
  gateway/schema/gateway.openrpc.json
```

Pass `--check` to verify the checked-in client without writing files.
