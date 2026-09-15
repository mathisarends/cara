import json
import re
from itertools import count
from typing import Any

import httpx
from agenttoolkit import Tool, Tools
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, SecretStr, create_model

_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


class McpServerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    url: AnyHttpUrl
    token: SecretStr | None = None


class McpTools(Tools):
    def __init__(self, servers: tuple[McpServerSettings, ...]) -> None:
        super().__init__()
        self._servers = servers
        self._clients: list[_McpClient] = []

    async def connect(self) -> None:
        pending: list[tuple[_McpClient, list[dict[str, Any]]]] = []
        try:
            for server in self._servers:
                if _NAME.fullmatch(server.name) is None:
                    raise ValueError(f"Invalid MCP server name: {server.name!r}")
                client = _McpClient(server)
                self._clients.append(client)
                pending.append((client, await client.connect()))
            for client, definitions in pending:
                for definition in definitions:
                    self.register(_remote_tool(client, definition))
        except BaseException:
            await self.aclose()
            raise

    async def aclose(self) -> None:
        clients, self._clients = self._clients, []
        for client in clients:
            await client.aclose()


class _McpClient:
    def __init__(self, settings: McpServerSettings) -> None:
        headers = {"Accept": "application/json, text/event-stream"}
        if settings.token is not None:
            headers["Authorization"] = f"Bearer {settings.token.get_secret_value()}"
        self.name = settings.name
        self._client = httpx.AsyncClient(
            base_url=str(settings.url),
            headers=headers,
            timeout=30,
        )
        self._ids = count(1)
        self._session_id: str | None = None

    async def connect(self) -> list[dict[str, Any]]:
        await self._request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "cara-gateway", "version": "0.1.0"},
            },
        )
        await self._notify("notifications/initialized")
        result = await self._request("tools/list", {})
        return result.get("tools", [])

    async def call(self, name: str, arguments: dict[str, Any]) -> object:
        result = await self._request(
            "tools/call",
            {"name": name, "arguments": arguments},
        )
        if result.get("isError"):
            raise RuntimeError(_render_content(result.get("content", [])))
        if "structuredContent" in result:
            return result["structuredContent"]
        return _render_content(result.get("content", []))

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.post(
            "",
            headers=self._session_headers,
            json={
                "jsonrpc": "2.0",
                "id": next(self._ids),
                "method": method,
                "params": params,
            },
        )
        response.raise_for_status()
        if session_id := response.headers.get("MCP-Session-Id"):
            self._session_id = session_id
        payload = _response_payload(response)
        if error := payload.get("error"):
            raise RuntimeError(f"MCP {self.name}: {error.get('message', error)}")
        return payload.get("result", {})

    async def _notify(self, method: str) -> None:
        response = await self._client.post(
            "",
            headers=self._session_headers,
            json={"jsonrpc": "2.0", "method": method},
        )
        response.raise_for_status()

    @property
    def _session_headers(self) -> dict[str, str]:
        return {} if self._session_id is None else {"MCP-Session-Id": self._session_id}


def _remote_tool(client: _McpClient, definition: dict[str, Any]) -> Tool:
    remote_name = definition["name"]
    exposed_name = f"{client.name}_{remote_name}"
    if _NAME.fullmatch(exposed_name) is None:
        raise ValueError(f"Invalid namespaced MCP tool name: {exposed_name!r}")
    schema = definition.get("inputSchema") or {"type": "object", "properties": {}}
    params = _parameter_model(exposed_name, schema)

    async def invoke(arguments: BaseModel) -> object:
        return await client.call(remote_name, arguments.model_dump(mode="json"))

    invoke.__annotations__["arguments"] = params

    return Tool(
        name=exposed_name,
        description=definition.get("description", ""),
        fn=invoke,
        param_model=params,
        parameters=schema,
        plugin_name=client.name,
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


def _response_payload(response: httpx.Response) -> dict[str, Any]:
    if "text/event-stream" not in response.headers.get("content-type", ""):
        return response.json()
    for line in response.text.splitlines():
        if line.startswith("data:"):
            return json.loads(line.removeprefix("data:").strip())
    raise RuntimeError("MCP stream ended without a JSON-RPC response")


def _render_content(content: list[dict[str, Any]]) -> str:
    texts = [item["text"] for item in content if item.get("type") == "text"]
    return "\n".join(texts) if texts else json.dumps(content, ensure_ascii=False)
