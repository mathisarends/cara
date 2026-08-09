from pathlib import Path

DEFAULT_MEMORY_DATABASE = Path("temp/cara-memory.db")
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


def cache_namespace(dimensions: int, dataset: str | None = None) -> str:
    base = f"{EMBEDDING_MODEL}:{dimensions}"
    return base if dataset is None else f"{base}:{dataset}"
