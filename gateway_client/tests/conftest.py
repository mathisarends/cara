import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_GENERATOR_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate_client.py"


@pytest.fixture(scope="session")
def generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_client", _GENERATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def build_spec() -> Callable[..., dict[str, Any]]:
    def build(
        schemas: dict[str, Any] | None = None,
        paths: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": paths or {},
            "components": {"schemas": schemas or {}},
        }

    return build


@pytest.fixture
def load_module() -> Callable[[str], dict[str, Any]]:
    def load(source: str) -> dict[str, Any]:
        namespace: dict[str, Any] = {}
        exec(compile(source, "<generated>", "exec"), namespace)
        return namespace

    return load
