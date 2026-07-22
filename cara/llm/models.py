from dataclasses import dataclass

from llmify import ChatModel


@dataclass(frozen=True)
class ModelProfile:
    name: str
    description: str
    model: ChatModel
