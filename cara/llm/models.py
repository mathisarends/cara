from dataclasses import dataclass

from llmify import ChatModel


@dataclass(frozen=True)
class ModelProfile:
    name: str
    description: str
    model: ChatModel

    def catalog_entry(self) -> str:
        return f"- {self.name}: {self.description}"
