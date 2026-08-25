# Gateway

The Gateway workspace area groups four independently installable Gateway
packages:

- [`server`](server#readme) (`gateway-server`) owns the FastAPI application,
  protocol, persistence, and schema generation.
- [`client`](client#readme) (`gateway-client`) provides the generated, typed
  Python client for that protocol.
- [`codegen`](codegen#readme) (`gateway-codegen`) owns the generator, templates,
  and drift test that produce the complete client source package.
- [`plugin_api`](plugin_api#readme) (`agent-plugin-api`) defines the stable,
  dependency-free contract between the server and agent plugins.

The packages remain separate `uv` workspace members so applications can depend
on the client without installing the server stack. Their Python import packages
remain `gateway`, `gateway_client`, and `gateway_codegen`, respectively.
