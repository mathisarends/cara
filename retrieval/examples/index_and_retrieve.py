import asyncio

from dotenv import load_dotenv

from retrieval import Document
from retrieval.memory import InMemoryVectorIndex
from retrieval.openai import OpenAICredentials, OpenAIEmbeddingModel, OpenAIEmbeddingProvider

load_dotenv(override=True)


async def main() -> None:
    credentials = OpenAICredentials()
    embedding_provider = OpenAIEmbeddingProvider(
        OpenAIEmbeddingModel.TEXT_EMBEDDING_3_SMALL,
        credentials=credentials,
    )
    index = InMemoryVectorIndex(embedding_provider)

    await index.index(
        [
            Document(
                id="cara",
                text="Cara ist ein sprachgesteuerter Assistent mit Terminal- und Voice-Sessions.",
            )
        ]
    )

    results = await index.retrieve("Wie kann ich mit Cara sprechen?", limit=1)
    for result in results:
        print(f"{result.score:.3f}: {result.document.text}")


if __name__ == "__main__":
    asyncio.run(main())
