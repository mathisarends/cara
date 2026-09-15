# gateway-server

Cara's central FastAPI process. It owns the JSON-RPC WebSocket API, sessions,
persistence, and the agent runtime. It composes [`agent`](../agent) directly;
shell/files run through the Sandbox Manager and custom tools through MCP.

```bash
docker compose up --build -d
```

For host development, set `CARA_GATEWAY_TOKEN` and run
`bash scripts/start_gateway.sh`. Configuration lives in
[`gateway.yaml`](../gateway.yaml). See the
[architecture vision](../AGENT_RUNTIME_ARCHITECTURE_VISION.md) and
[MCP guide](../docs/mcp-tools.md).
