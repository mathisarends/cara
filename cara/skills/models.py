from pydantic import BaseModel, ConfigDict


class Skill(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    description: str
    instructions: str
    resources: tuple[str, ...] = ()

    def catalog_entry(self) -> str:
        return f"- {self.name}: {self.description}"
