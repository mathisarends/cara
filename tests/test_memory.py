from datetime import date
from pathlib import Path

from cara.memory import MemoryStore
from cara.messages import MessageManager


def _store(root: Path) -> MemoryStore:
    return MemoryStore(root=root, today=lambda: date(2026, 8, 2))


def test_memory_renders_core_files_in_order(tmp_path: Path) -> None:
    (tmp_path / "SOUL.md").write_text("Ich bin Cara.", encoding="utf-8")
    (tmp_path / "USER.md").write_text("Mathis lebt in Berlin.", encoding="utf-8")

    assert _store(tmp_path).render() == ("<soul>\nIch bin Cara.\n</soul>\n\n<user>\nMathis lebt in Berlin.\n</user>")


def test_memory_includes_only_todays_daily_note(tmp_path: Path) -> None:
    daily = tmp_path / "daily"
    daily.mkdir()
    (daily / "2026-08-01.md").write_text("Gestern.", encoding="utf-8")
    (daily / "2026-08-02.md").write_text("Heute.", encoding="utf-8")

    assert _store(tmp_path).render() == "<daily>\nHeute.\n</daily>"


def test_memory_skips_missing_and_empty_files(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text("   \n", encoding="utf-8")

    assert _store(tmp_path).render() == ""


def test_memory_is_wrapped_in_a_memory_block(tmp_path: Path) -> None:
    (tmp_path / "SOUL.md").write_text("Ich bin Cara.", encoding="utf-8")
    messages = MessageManager(system_prompt="System", memory=_store(tmp_path))

    rendered = messages.to_llm_messages()[0].content

    assert rendered == "System\n\n<memory>\n<soul>\nIch bin Cara.\n</soul>\n</memory>"


def test_packaged_memory_is_loaded_by_default() -> None:
    assert "<soul>" in MemoryStore().render()
