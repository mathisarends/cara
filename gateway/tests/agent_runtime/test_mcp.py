import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from gateway.agent_runtime import mcp as mcp_module
from gateway.agent_runtime.mcp import McpServerSettings, McpTools


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> MCPServer:
    server = MCPServer("company")

    @server.tool(description="Look up a value.")
    def lookup(key: str) -> dict[str, str]:
        return {"value": key}

    @server.tool(description="Always fails.")
    def explode() -> str:
        raise ToolError("boom")

    monkeypatch.setattr(
        mcp_module,
        "Client",
        lambda _transport, **kwargs: Client(server, **kwargs),
    )
    return server


async def test_mcp_tools_are_discovered_namespaced_and_called(server) -> None:
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
    try:
        lookup = tools.get("company_lookup")
        result = await tools.execute("company_lookup", {"key": "cara"})
        with pytest.raises(RuntimeError, match="boom"):
            await tools.execute("company_explode", {})
    finally:
        await tools.aclose()

    assert lookup is not None
    assert lookup.description == "Look up a value."
    assert lookup.plugin_name == "company"
    assert lookup.local_name == "lookup"
    assert result == {"value": "cara"}
