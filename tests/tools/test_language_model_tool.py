import asyncio

from cara.llm import LanguageModels, ModelProfile
from cara.tools import ActionResult, Tools


def _registry() -> LanguageModels:
    return LanguageModels(
        [
            ModelProfile("fast", "Quick replies.", object()),
            ModelProfile("deep", "Careful reasoning.", object()),
        ]
    )


def test_set_language_model_tool_switches_the_injected_registry() -> None:
    models = _registry()
    tools = Tools()
    tools.provide(models)

    result = asyncio.run(tools.execute("set_language_model", {"name": "deep"}))

    assert result == ActionResult.success("Language model switched to 'deep'.")
    assert models.active().name == "deep"


def test_set_language_model_tool_rejects_an_unknown_profile() -> None:
    models = _registry()
    tools = Tools()
    tools.provide(models)

    result = asyncio.run(tools.execute("set_language_model", {"name": "turbo"}))

    assert result == ActionResult.fail("Unknown language model 'turbo'. Available: fast, deep")
    assert models.active().name == "fast"


def test_language_model_tool_is_only_available_with_alternatives() -> None:
    tools = Tools()
    tools.provide(LanguageModels.single(object()))

    assert tools.get("set_language_model") is None
    assert all(schema["function"]["name"] != "set_language_model" for schema in tools.to_schema())


def test_language_model_tool_description_lists_the_profiles_and_active_one() -> None:
    tools = Tools()
    tools.provide(_registry())

    schema = next(item for item in tools.to_schema() if item["function"]["name"] == "set_language_model")
    description = schema["function"]["description"]

    assert "Currently active: 'fast'." in description
    assert description.endswith("Available profiles: fast: Quick replies.; deep: Careful reasoning.")
