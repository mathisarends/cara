from collections.abc import Sequence

from openai import AsyncOpenAI

from retrieval import Embedding, EmbeddingProvider
from retrieval.openai.credentials import OpenAICredentials


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        model: str,
        *,
        credentials: OpenAICredentials,
        client: AsyncOpenAI | None = None,
        dimensions: int | None = None,
    ) -> None:
        self._model = model
        self._client = client if client is not None else AsyncOpenAI(api_key=credentials.api_key.get_secret_value())
        self._dimensions = dimensions

    async def embed(self, texts: Sequence[str]) -> list[Embedding]:
        inputs = list(texts)
        if self._dimensions is None:
            response = await self._client.embeddings.create(
                input=inputs,
                model=self._model,
                encoding_format="float",
            )
        else:
            response = await self._client.embeddings.create(
                input=inputs,
                model=self._model,
                dimensions=self._dimensions,
                encoding_format="float",
            )

        return [list(item.embedding) for item in sorted(response.data, key=lambda item: item.index)]
