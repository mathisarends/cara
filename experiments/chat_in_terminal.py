import asyncio
from pathlib import Path

from agenttoolkit import Skills
from dotenv import load_dotenv
from llmify import ChatCodex

from cara import Agent, TerminalSession
from cara.memory import DEFAULT_MEMORY_DATABASE, HybridMemorySearch
from cara.tools import build_tools

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = PROJECT_ROOT / "skills"


async def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    skills = Skills.from_local_dir(SKILLS_ROOT)
    llm = ChatCodex.from_cli(model="gpt-5.6-terra")

    agent = Agent(
        llm=llm,
        tools=build_tools(
            HybridMemorySearch(PROJECT_ROOT / DEFAULT_MEMORY_DATABASE),
            skills=skills,
            workspace_mounts={"/skills": SKILLS_ROOT},
        ),
        skills=skills,
        extend_system_prompt=(
            "Die lokalen Skills sind unter `/skills` schreibbar eingebunden. "
            "Lies bestehende Dateien vor Änderungen und speichere neue oder geänderte Skills dort."
        ),
    )

    terminal_session = TerminalSession(agent)
    await terminal_session.run()


if __name__ == "__main__":
    asyncio.run(main())
