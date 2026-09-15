import json

import httpx

from gateway.agent_runtime.mcp import McpServerSettings, McpTools


async def test_mcp_tools_are_discovered_namespaced_and_called(monkeypatch) -> None:
    methods: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        methods.append(payload["method"])
        if payload["method"] == "initialize":
            return httpx.Response(
                200,
                headers={"MCP-Session-Id": "session-1"},
                json={"jsonrpc": "2.0", "id": payload["id"], "result": {}},
            )
        if payload["method"] == "notifications/initialized":
            assert request.headers["MCP-Session-Id"] == "session-1"
            return httpx.Response(202)
        if payload["method"] == "tools/list":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {
                        "tools": [
                            {
                                "name": "lookup",
                                "description": "Look up a value.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"key": {"type": "string"}},
                                    "required": ["key"],
                                },
                            }
                        ]
                    },
                },
            )
        assert payload["method"] == "tools/call"
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {
                    "structuredContent": {
                        "value": payload["params"]["arguments"]["key"]
                    }
                },
            },
        )

    transport = httpx.MockTransport(handle)
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=transport, **kwargs),
    )
    tools = McpTools(
        (
            McpServerSettings(
                name="company",
                url="http://company-tools:8080/mcp",
                token="secret",
            ),
        )
    )

    await tools.connect()
    result = await tools.execute("company_lookup", {"key": "cara"})
    await tools.aclose()

    assert result == {"value": "cara"}
    assert methods == [
        "initialize",
        "notifications/initialized",
        "tools/list",
        "tools/call",
    ]
