# Agent Instructions

- Package `__init__.py` files that re-export symbols from sibling modules must use explicit relative imports, for example `from .module import PublicName`.
- Otherwise, prefer absolute imports from the `cara` package, for example `from cara.events import EventBus`.
- Re-export only the intended public API from package `__init__.py` files. Keep implementation details private to their modules and list exported names in `__all__` when a package exposes a curated API.
- Do not add `from __future__ import annotations` defensively by default; the project targets Python 3.14, so only use it when a concrete compatibility reason requires it.
- Avoid defensive `getattr` probing for known APIs. Prefer concrete types, typed protocols, or explicit branches over duck-typed fallback logic unless the code genuinely supports multiple external shapes.
