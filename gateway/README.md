# gateway-server

Cara's central FastAPI process. It owns the REST resource API, the JSON-RPC
WebSocket for live turns ([transport split](../docs/gateway-transport.md)), sessions,
persistence, and the agent runtime. It composes [`agent`](../agent) directly
and owns the complete concrete tool catalog. Shell/files run through the
Sandbox Manager and external custom tools through MCP.

```bash
docker compose up --build -d
```

For host development, set `CARA_GATEWAY_TOKEN` and run
`uv run --package gateway-server gateway-migrate` followed by
`uv run --package gateway-server cara-gateway`. Configuration lives in
[`gateway.yaml`](../gateway.yaml). The Gateway owns workspace configuration and
the Sandbox Manager client lifecycle, then injects the resulting workspace and
command-runner capabilities into the agent. See the
[MCP guide](../docs/mcp-tools.md).
