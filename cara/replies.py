from collections.abc import AsyncIterator

from llmify import ChatInvokeCompletion, StreamEnd, StreamEvent, StreamTextDelta, StreamToolCall

from cara.speech.streaming import NaturalPauseChunker, TextChunkStream


class StreamingReply:
    def __init__(
        self,
        events: AsyncIterator[StreamEvent],
        chunker: NaturalPauseChunker,
    ) -> None:
        self._events = events
        self._chunker = chunker
        self._text_chunks = TextChunkStream()
        self._completion: ChatInvokeCompletion[str] | None = None

    @property
    def text_chunks(self) -> AsyncIterator[str]:
        return self._text_chunks

    async def collect(self) -> ChatInvokeCompletion[str]:
        collected = False
        try:
            async for event in self._events:
                match event:
                    case StreamTextDelta(delta=delta):
                        for sentence in self._chunker.add(delta):
                            self._text_chunks.send(sentence)
                    case StreamToolCall():
                        continue
                    case StreamEnd() as end:
                        self._completion = ChatInvokeCompletion(
                            completion=end.completion,
                            usage=end.usage,
                            stop_reason=end.stop_reason,
                            tool_calls=end.tool_calls,
                        )

            if self._completion is None:
                raise RuntimeError("LLM stream ended without a final event.")
            collected = True
            return self._completion
        finally:
            if not collected:
                self.close()

    def announce(self, text: str) -> None:
        """Queue an interim spoken sentence (e.g. a tool-call status) ahead of the answer."""
        self._text_chunks.send(text)

    def finish(self, answer: str) -> None:
        if self._completion is None:
            raise RuntimeError("Cannot finish a reply before collecting its completion.")

        streamed_answer = self._completion.completion.strip()
        if answer == streamed_answer:
            if tail := self._chunker.flush():
                self._text_chunks.send(tail)
        elif answer:
            self._text_chunks.send(answer)
        self.close()

    def close(self) -> None:
        self._text_chunks.close()
