# Gateway client code generator

`gateway-codegen` turns the Gateway server's checked-in OpenRPC schema into the
complete `gateway_client` Python source package. Generator implementation,
templates, and drift tests live here so the generated client package contains
no tooling of its own.

From the repository root:

```bash
uv run --package gateway-server cara-gateway-schema
uv run --package gateway-codegen cara-gateway-client-generate \
  gateway/server/schema/gateway.openrpc.json
```

Use `--check` to verify the checked-in client without writing files:

```bash
uv run --package gateway-codegen cara-gateway-client-generate \
  gateway/server/schema/gateway.openrpc.json --check
```

The default output is `gateway/client/src/gateway_client`. Every Python file in
that directory is generated and must not be edited manually.
