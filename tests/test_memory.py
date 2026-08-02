from datetime import date
from pathlib import Path

from cara.memory import MemoryStore
from cara.messages import MessageManager


def _store(root: Path) -> MemoryStore:
    return MemoryStore(root=root, today=lambda: date(2026, 8, 2))


def test_memory_renders_files_in_order(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text("Halbmarathon im Oktober.", encoding="utf-8")
    (tmp_path / "DREAMS.md").write_text("Alles bleibt lokal.", encoding="utf-8")

    assert _store(tmp_path).render() == (
        "<memory>\nHalbmarathon im Oktober.\n</memory>\n\n<dreams>\nAlles bleibt lokal.\n</dreams>"
    )


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
    (tmp_path / "DREAMS.md").write_text("Alles bleibt lokal.", encoding="utf-8")
    messages = MessageManager(system_prompt="System", memory=_store(tmp_path))

    rendered = messages.to_llm_messages()[0].content

    assert rendered == "System\n\n<memory>\n<dreams>\nAlles bleibt lokal.\n</dreams>\n</memory>"


def test_packaged_memory_is_loaded_by_default() -> None:
    assert "<memory>" in MemoryStore().render()
