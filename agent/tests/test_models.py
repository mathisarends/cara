from typing import cast

import pytest
from llmify import ChatModel

from agent.models import ModelSwitch


def test_model_switch_exposes_and_switches_named_models() -> None:
    first = cast(ChatModel, object())
    second = cast(ChatModel, object())
    models = ModelSwitch({"first": first, "second": second}, default="first")

    assert models.current is first
    assert models.current_name == "first"
    assert models.names == ("first", "second")
    assert models.has_alternatives

    models.switch("second")

    assert models.current is second
    assert models.current_name == "second"


def test_model_switch_rejects_an_unknown_model() -> None:
    models = ModelSwitch.single(cast(ChatModel, object()), name="first")

    with pytest.raises(ValueError, match="Unknown model 'missing'"):
        models.switch("missing")
