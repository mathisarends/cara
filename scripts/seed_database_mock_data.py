import argparse
import asyncio
from pathlib import Path

from dotenv import load_dotenv

from cara.memory import DEFAULT_MEMORY_DATABASE, index_memory_directory

load_dotenv()

MOCK_DATASET = "mock-memory-v1"
MOCK_MEMORY_DIRECTORY = Path(__file__).parent / "mock_data" / "memory"


async def main(database: Path) -> None:
    count = await index_memory_directory(
        MOCK_MEMORY_DIRECTORY,
        database,
        dataset=MOCK_DATASET,
    )
    print(f"Indexed {count} mock memory documents into {database}.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed the SQLite memory index with mock Markdown notes."
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_MEMORY_DATABASE)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(_parse_args().database))
