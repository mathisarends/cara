# Gateway

Workspace area grouping four independently installable Gateway packages:

- [`server`](server#readme) (`gateway-server`) — FastAPI app, protocol,
  persistence, schema generation.
- [`client`](client#readme) (`gateway-client`) — generated, typed Python
  client for that protocol.
- [`codegen`](codegen#readme) (`gateway-codegen`) — the generator wrapper,
  and drift test producing the client source.
- [`plugin_api`](plugin_api#readme) (`agent-plugin-api`) — stable,
  dependency-free contract between the server and agent plugins.

Kept as separate `uv` workspace members so applications can depend on the
client without installing the server stack. Import packages: `gateway`,
`gateway_client`, `gateway_codegen`, `agent_plugin_api`.
