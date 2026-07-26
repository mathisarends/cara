import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from cara.file_system import Workspace
from cara.subagent import Subagent
from cara.tools import Tools
from cara.tools.handler import DockerBashSandbox

_SYSTEM_PROMPT = """
You are an interactive test agent for a Bash sandbox. Use the bash tool for
shell requests. Briefly report the command's output or explain its failure.
The shell runs inside an isolated container whose only writable mount is the
workspace. The image includes a small example CLI named cara-tool; inspect it
with `cara-tool --help` when the user asks to try the bundled CLI. Spotifyify
is installed with network access and runtime-provided Spotify credentials.
Use its JSON output and select only fields needed for the answer.
"""


async def main() -> None:
    load_dotenv(override=True)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    default_spotify_cache = Path(__file__).resolve().parents[2] / "spotifyify" / ".cache"
    spotify_cache = Path(os.environ.get("SPOTIFY_CACHE_PATH", default_spotify_cache))
    tools = Tools(
        bash_sandbox=DockerBashSandbox(
            spotify_cache_path=spotify_cache if spotify_cache.is_file() else None,
        )
    )
    workspace = tools.resolve(Workspace)
    if workspace is None:
        raise RuntimeError("Tools did not configure a workspace.")

    agent = Subagent(tools=tools, system_prompt=_SYSTEM_PROMPT)

    print("Cara Bash sandbox")
    print(f"Workspace: {workspace.root}")
    print("Enter a request, or /exit to stop.")

    while True:
        try:
            prompt = await asyncio.to_thread(input, "\nyou> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if prompt.strip() == "/exit":
            break
        if not prompt.strip():
            continue

        try:
            answer = await agent.run(prompt)
        except Exception:
            logging.exception("Request failed")
        else:
            print(f"\ncara> {answer}")


if __name__ == "__main__":
    asyncio.run(main())
