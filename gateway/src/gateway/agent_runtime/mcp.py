import json
import re
from contextlib import AsyncExitStack
from typing import Any

import httpx2
from agenttoolkit import Tool, Tools
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, ContentBlock, Implementation, TextContent
from mcp.types import Tool as McpTool
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, SecretStr, create_model

_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
_CLIENT_INFO = Implementation(name="cara-gateway", version="0.1.0")


class McpServerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    url: AnyHttpUrl
    token: SecretStr | None = None


class McpTools(Tools):
    def __init__(self, servers: tuple[McpServerSettings, ...]) -> None:
        super().__init__()
        self._servers = servers
        self._stack = AsyncExitStack()

    async def connect(self) -> None:
        try:
            pending: list[Tool] = []
            for server in self._servers:
                if _NAME.fullmatch(server.name) is None:
                    raise ValueError(f"Invalid MCP server name: {server.name!r}")
                client = await self._open(server)
                pending.extend(
                    _remote_tool(server.name, client, definition)
                    for definition in await _list_tools(client)
                )
            for tool in pending:
                self.register(tool)
        except BaseException:
            await self.aclose()
            raise

    async def aclose(self) -> None:
        stack, self._stack = self._stack, AsyncExitStack()
        await stack.aclose()

    async def _open(self, server: McpServerSettings) -> Client:
        http_client = await self._stack.enter_async_context(
            httpx2.AsyncClient(
                headers=_auth_headers(server),
                timeout=httpx2.Timeout(30.0, read=300.0),
                follow_redirects=True,
            )
        )
        transport = streamable_http_client(str(server.url), http_client=http_client)
        return await self._stack.enter_async_context(
            Client(transport, client_info=_CLIENT_INFO)
        )


def _auth_headers(server: McpServerSettings) -> dict[str, str]:
    if server.token is None:
        return {}
    return {"Authorization": f"Bearer {server.token.get_secret_value()}"}


async def _list_tools(client: Client) -> list[McpTool]:
    tools: list[McpTool] = []
    cursor: str | None = None
    while True:
        page = await client.list_tools(cursor=cursor)
        tools.extend(page.tools)
        if page.next_cursor is None:
            return tools
        cursor = page.next_cursor


def _remote_tool(server_name: str, client: Client, definition: McpTool) -> Tool:
    remote_name = definition.name
    exposed_name = f"{server_name}_{remote_name}"
    if _NAME.fullmatch(exposed_name) is None:
        raise ValueError(f"Invalid namespaced MCP tool name: {exposed_name!r}")
    schema = definition.input_schema or {"type": "object", "properties": {}}
    params = _parameter_model(exposed_name, schema)

    async def invoke(arguments: BaseModel) -> object:
        result = await client.call_tool(
            remote_name,
            arguments.model_dump(mode="json", exclude_unset=True),
        )
        return _tool_output(server_name, remote_name, result)

    invoke.__annotations__["arguments"] = params

    return Tool(
        name=exposed_name,
        description=definition.description or "",
        fn=invoke,
        param_model=params,
        parameters=schema,
        plugin_name=server_name,
        local_name=remote_name,
    )


def _parameter_model(name: str, schema: dict[str, Any]) -> type[BaseModel]:
    required = set(schema.get("required", []))
    fields = {
        field_name: (Any, ... if field_name in required else None)
        for field_name in schema.get("properties", {})
    }
    return create_model(
        f"{name.title().replace('_', '')}Params",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


def _tool_output(server_name: str, tool_name: str, result: CallToolResult) -> object:
    if result.is_error:
        raise RuntimeError(
            f"MCP {server_name}_{tool_name}: {_render_content(result.content)}"
        )
    if result.structured_content is not None:
        return result.structured_content
    return _render_content(result.content)


def _render_content(content: list[ContentBlock]) -> str:
    texts = [block.text for block in content if isinstance(block, TextContent)]
    if texts:
        return "\n".join(texts)
    return json.dumps(
        [block.model_dump(mode="json", by_alias=True) for block in content],
        ensure_ascii=False,
    )
