# MCP tools

Cara loads user and integration tools from out-of-process MCP servers. The
Gateway remains the agent runtime; an MCP server only publishes tool schemas and
executes calls for its own integration.

## Gateway configuration

Configure Streamable HTTP endpoints in `gateway.yaml`:

```yaml
tools:
  - name: github
    url: http://github-tools:8080/mcp
    token: replace-me
  - name: company
    url: http://company-tools:8080/mcp
```

`name` is a stable namespace containing letters, numbers, `_` or `-`. A remote
tool called `search` from the `github` server is exposed to the model as
`github_search`. Duplicate exposed names fail Gateway startup.

The Gateway connects once during startup, performs MCP initialization and
`tools/list`, and caches the resulting schemas. It does not rediscover tools on
every model step. A connection or schema failure prevents startup so the model
never receives a partially configured catalog.

When `token` is present, Cara sends it as an HTTP Bearer token. Production
tokens should be supplied through deployment secrets rather than committed to
`gateway.yaml`.

## Minimal Python tool server

Create a separate workspace member or repository. A minimal package needs the
official MCP Python SDK:

```toml
[project]
name = "company-tools"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = ["mcp"]
```

Implement the server:

```python
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("company-tools")


@mcp.tool()
async def lookup_customer(customer_id: str) -> dict[str, object]:
    """Look up one customer by its stable customer ID."""
    return {"customer_id": customer_id, "status": "active"}


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=8080,
        stateless_http=True,
        json_response=True,
    )
```

The endpoint is `/mcp` by default. Stateless JSON responses are the simplest
fit for Cara's current client. Streamable HTTP responses containing a single
JSON-RPC result are also accepted.

Give every tool:

- a stable, concise name;
- a docstring that says when it should be used;
- typed parameters, so MCP publishes an object-shaped JSON Schema;
- structured output where callers benefit from machine-readable fields;
- explicit errors without secrets or internal stack traces.

## Compose integration

Build the tool host as its own service on the private Compose network:

```yaml
services:
  company-tools:
    build: ./company_tools
    environment:
      COMPANY_API_TOKEN: ${COMPANY_API_TOKEN}
    expose:
      - "8080"
```

Then use `http://company-tools:8080/mcp` in `gateway.yaml`. Do not publish the
port to the host unless humans or systems outside the stack must reach it.

An MCP tool server must not receive:

- the Docker socket;
- the Gateway database;
- the workspace or CLI credential volumes unless its specific job requires a
  narrowly scoped mount;
- unrelated service credentials.

The Gateway's Codex credential is unrelated to MCP credentials. Compose mounts
the host Codex home at `/root/.codex` because the model client runs in the
Gateway. MCP tool hosts and sandbox containers never receive that mount.

## Authentication

The tool host is responsible for validating the configured Bearer token. Keep
Gateway-to-tool traffic on a private network even when authentication is
enabled. Use a different token for each server so one compromised integration
cannot impersonate another.

For a local trusted server, authentication can initially be omitted. It should
not be omitted when the endpoint is published or another container on the
network is not trusted.

## Current supported MCP surface

Cara currently implements the MCP operations required for tools:

- `initialize` and `notifications/initialized`;
- `tools/list` during Gateway startup;
- `tools/call` during an agent turn;
- JSON and single-result Server-Sent Event responses;
- optional `MCP-Session-Id` propagation;
- text and `structuredContent` results.

Sampling, elicitation, resources, prompts, progress callbacks, server-initiated
notifications and resumable streams are not part of the initial tool-host
contract. Add them through the MCP adapter when a concrete integration needs
them; they must not leak into the agent loop.

## Verification

Before adding the server to Cara:

1. Start it independently and verify `/mcp` with the MCP Inspector or SDK
   client.
2. Confirm `tools/list` contains the expected descriptions and schemas.
3. Call each tool with valid and invalid arguments.
4. Start the Gateway and confirm the namespaced tools appear once.
5. Verify that a tool-host outage fails clearly and never executes local Python
   code inside the Gateway.

The official MCP Python SDK documents Streamable HTTP server deployment and
provides an Inspector-compatible development workflow:
<https://github.com/modelcontextprotocol/python-sdk>.
