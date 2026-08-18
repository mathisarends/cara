from unittest.mock import AsyncMock

import pytest

from voice.events.listener.light_listener import LightVisualization


@pytest.fixture
def light_visualization() -> AsyncMock:
    return AsyncMock(spec=LightVisualization)
