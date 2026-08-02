import argparse
import asyncio
from pathlib import Path

from cara.memory import DEFAULT_MEMORY_DATABASE, delete_memory_dataset

MOCK_DATASET = "mock-memory-v1"
MOCK_MEMORY_DIRECTORY = Path(__file__).parent / "mock_data" / "memory"


async def main(database: Path) -> None:
    count = await delete_memory_dataset(database, MOCK_MEMORY_DIRECTORY, dataset=MOCK_DATASET)
    print(f"Deleted {count} mock memory documents from {database}.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Delete only the seeded mock notes from the SQLite memory index.")
    parser.add_argument("--database", type=Path, default=DEFAULT_MEMORY_DATABASE)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(_parse_args().database))
