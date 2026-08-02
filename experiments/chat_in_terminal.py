import asyncio
from pathlib import Path

from agenttoolkit import Skills
from dotenv import load_dotenv
from llmify import ChatCodex

from cara import Agent, TerminalSession
from cara.tools import build_tools

PROJECT_ROOT = Path(__file__).resolve().parents[1]


async def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    skills = Skills.from_local_dir(PROJECT_ROOT / "skills")
    llm = ChatCodex.from_cli(model="gpt-5.6-terra")

    agent = Agent(
        llm=llm,
        tools=build_tools(skills=skills),
        skills=skills,
    )

    terminal_session = TerminalSession(agent)
    await terminal_session.run()


if __name__ == "__main__":
    asyncio.run(main())
