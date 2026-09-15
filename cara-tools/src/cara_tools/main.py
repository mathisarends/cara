import os

from cara_tools.server import mcp


def main() -> None:
    mcp.run(
        transport="streamable-http",
        host=os.environ.get("CARA_TOOLS_HOST", "127.0.0.1"),
        port=int(os.environ.get("CARA_TOOLS_PORT", "8080")),
        streamable_http_path="/mcp",
    )


if __name__ == "__main__":
    main()
