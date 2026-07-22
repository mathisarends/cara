import pytest

from cara.llm import LanguageModels, ModelProfile


def _profiles() -> list[ModelProfile]:
    return [
        ModelProfile("fast", "Quick replies.", object()),
        ModelProfile("deep", "Careful reasoning.", object()),
    ]


def test_single_wraps_one_default_profile() -> None:
    models = LanguageModels.single(object())

    assert models.names() == ["default"]
    assert models.active().name == "default"
    assert models.has_alternatives() is False


def test_current_and_active_follow_the_selection() -> None:
    profiles = _profiles()
    models = LanguageModels(profiles)

    assert models.active().name == "fast"
    assert models.current() is profiles[0].model

    models.select("deep")

    assert models.active().name == "deep"
    assert models.current() is profiles[1].model


def test_select_returns_the_profile_and_rejects_unknown_names() -> None:
    models = LanguageModels(_profiles())

    assert models.select("deep").name == "deep"

    with pytest.raises(ValueError, match="Unknown language model 'turbo'. Available: fast, deep"):
        models.select("turbo")


def test_get_returns_none_for_unknown_names() -> None:
    models = LanguageModels(_profiles())

    assert models.get("nope") is None
    assert models.get("fast").name == "fast"


def test_describe_profiles_lists_name_and_description_in_order() -> None:
    models = LanguageModels(_profiles())

    assert models.describe_profiles() == "fast: Quick replies.; deep: Careful reasoning."


def test_has_alternatives_is_true_with_multiple_profiles() -> None:
    assert LanguageModels(_profiles()).has_alternatives() is True


def test_explicit_active_profile_is_selected() -> None:
    models = LanguageModels(_profiles(), active="deep")

    assert models.active().name == "deep"


def test_unknown_active_profile_raises() -> None:
    with pytest.raises(ValueError, match="Unknown active model profile 'ghost'"):
        LanguageModels(_profiles(), active="ghost")


def test_empty_registry_raises() -> None:
    with pytest.raises(ValueError, match="at least one model profile"):
        LanguageModels([])
