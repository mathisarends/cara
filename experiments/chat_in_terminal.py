import asyncio
import os
from pathlib import Path

from agenttoolkit import Skills
from agenttoolkit.builtins import BindMount, LocalWorkspace
from dotenv import load_dotenv
from transitbus import EventBus

from cara import Agent, HueListener, TerminalSession
from cara.codex import CodexModel, create_codex_model
from cara.tools import build_tools

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SKILLS_ROOT = _PROJECT_ROOT / "skills"
_WORKSPACE_ROOT = _PROJECT_ROOT / "workspace"

load_dotenv()


def _spogo_config_root() -> Path:
    app_data = os.environ.get("APPDATA")
    if app_data is None:
        raise RuntimeError("APPDATA is required to locate the Spogo configuration on Windows.")
    config_root = Path(app_data) / "spogo"
    if not config_root.is_dir():
        raise FileNotFoundError(f"Spogo configuration directory does not exist: {config_root}")
    return config_root


async def main() -> None:
    skills = Skills.from_dir(_SKILLS_ROOT)
    llm = create_codex_model(CodexModel.TERRA)
    event_bus = EventBus()
    hue_listener = HueListener(event_bus)

    async with build_tools(
        skills=skills,
        workspace=LocalWorkspace(
            _WORKSPACE_ROOT,
            mounts={
                "/src/cara": _PROJECT_ROOT / "cara",
                "/experiments": _PROJECT_ROOT / "experiments",
                "/skills": _SKILLS_ROOT,
            },
        ),
        sandbox_environment={"SPOGO_CONFIG": "/etc/spogo.toml"},
        sandbox_mounts=(
            BindMount.read_write(_PROJECT_ROOT / "cara", "/src/cara"),
            BindMount.read_write(_PROJECT_ROOT / "experiments", "/experiments"),
            BindMount.read_write(_SKILLS_ROOT, "/skills"),
            BindMount.read_write(_spogo_config_root(), "/spogo"),
            BindMount.read_only(_PROJECT_ROOT / "docker" / "spogo.toml", "/etc/spogo.toml"),
        ),
        sandbox_network_access=True,
    ) as tools:
        agent = Agent(
            llm=llm,
            tools=tools,
            prompt_root=_WORKSPACE_ROOT,
            skills=skills,
            extend_system_prompt=(
                "Die lokalen Skills sind unter `/skills` schreibbar eingebunden. "
                "Lies bestehende Dateien vor Änderungen und speichere neue oder geänderte Skills dort."
            ),
            event_bus=event_bus,
        )

        terminal_session = TerminalSession(agent, event_bus=event_bus)
        try:
            await terminal_session.run()
        finally:
            await hue_listener.close()


if __name__ == "__main__":
    asyncio.run(main())
