# Gateway

The Gateway workspace area groups the two independently installable Gateway
packages:

- [`server`](server#readme) (`gateway-server`) owns the FastAPI application,
  protocol, persistence, and schema generation.
- [`client`](client#readme) (`gateway-client`) provides the generated, typed
  Python client for that protocol.

The packages remain separate `uv` workspace members so applications can depend
on the client without installing the server stack. Their Python import packages
remain `gateway` and `gateway_client`, respectively.
