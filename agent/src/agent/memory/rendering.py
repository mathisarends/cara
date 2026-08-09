from collections.abc import Sequence

from agent.memory.service import HybridMemoryResult


def render_memory_results(results: Sequence[HybridMemoryResult]) -> str:
    if not results:
        return "(no relevant memories found)"

    grouped: dict[str, tuple[str, str | None, list[str]]] = {}
    for result in results:
        document = result.document
        path = document.metadata.get("path")
        source = path if isinstance(path, str) else document.parent_id or document.id
        group_key = document.parent_id or document.id
        created_at = (
            document.created_at.date().isoformat()
            if document.created_at is not None
            else None
        )
        text = document.text.strip()

        group = grouped.get(group_key)
        if group is None:
            grouped[group_key] = (source, created_at, [text])
        elif text not in group[2]:
            group[2].append(text)

    rendered = ["Memory excerpts, ordered by relevance:"]
    for source, created_at, excerpts in grouped.values():
        heading = f"[{source}]" if created_at is None else f"[{source} | {created_at}]"
        rendered.append(f"{heading}\n" + "\n\n".join(excerpts))
    return "\n\n".join(rendered)
