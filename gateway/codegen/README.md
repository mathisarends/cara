# gateway-codegen

Turns the Gateway server's checked-in OpenRPC schema into the complete
[`gateway_client`](../client) Python source package. Generator, templates,
and drift tests live here so the generated client contains no tooling of its
own.

```bash
uv run --package gateway-server cara-gateway-schema
uv run --package gateway-codegen cara-gateway-client-generate \
  gateway/server/schema/gateway.openrpc.json
```

`--check` verifies the checked-in client without writing files — used in CI.

## Dependencies

- Reads [`gateway-server`](../server)'s exported `gateway.openrpc.json`.
- Writes into [`gateway-client`](../client); every generated file there is
  produced from this package and must not be hand-edited.
