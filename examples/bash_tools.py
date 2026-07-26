import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from llmify import CerebrasModel, ChatCerebras

from cara.file_system import Workspace
from cara.subagent import Subagent
from cara.tools import BashSandboxConfig, BashSandboxMount, Tools

_SPOTIFY_ENVIRONMENT = (
    "SPOTIFY_CLIENT_ID",
    "SPOTIFY_CLIENT_SECRET",
    "SPOTIFY_REDIRECT_URI",
    "SPOTIFY_ACCESS_TOKEN",
    "SPOTIFY_REFRESH_TOKEN",
    "SPOTIFY_TOKEN_EXPIRES_AT",
)

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
    mounts = (BashSandboxMount(spotify_cache, "/workspace/.cache", read_only=False),) if spotify_cache.is_file() else ()
    tools = Tools(
        bash_sandbox_config=BashSandboxConfig(
            image="cara-bash-sandbox:latest",
            network="bridge",
            forwarded_environment=_SPOTIFY_ENVIRONMENT,
            mounts=mounts,
        ),
    )
    workspace = tools.resolve(Workspace)
    if workspace is None:
        raise RuntimeError("Tools did not configure a workspace.")

    llm = ChatCerebras(model=CerebrasModel.ZAI_GLM_4_7_PREVIEW)
    agent = Subagent(llm=llm, tools=tools, system_prompt=_SYSTEM_PROMPT)

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
