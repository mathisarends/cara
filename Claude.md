# Agent Instructions

- Package `__init__.py` files that re-export symbols from sibling modules must use explicit relative imports, for example `from .module import PublicName`.
- Otherwise, prefer absolute imports from the `cara` package, for example `from cara.events import EventBus`.
- Re-export only the intended public API from package `__init__.py` files. Keep implementation details private to their modules and list exported names in `__all__` when a package exposes a curated API.
- Be deliberately restrictive about what a package `__init__.py` re-exports: expose only the symbols external callers actually need and would reasonably expect as the package's interface, never a blanket re-export of everything the modules define. Credentials/settings objects, internal helpers, single-value enums, and other implementation details stay private and are imported from their modules where needed.
- Do not add `from __future__ import annotations` defensively by default; the project targets Python 3.14, so only use it when a concrete compatibility reason requires it.
- Avoid defensive `getattr` probing for known APIs. Prefer concrete types, explicit branches, or abstract base classes over duck-typed fallback logic unless the code genuinely supports multiple external shapes.
- Define abstraction boundaries with abstract base classes (`abc.ABC` + `@abstractmethod`), not `typing.Protocol`. Prefer ABCs for any interface the project owns and implements.
- Use dataclasses only for classes that are primarily data containers. Prefer regular classes when a class owns significant behavior or validation logic.
- Keep class attributes and instance variables private by default. Expose public attributes only when they are intentionally part of the public API.
- Prefer private module-level helper functions for module-local or cross-module logic instead of static methods that do not need class state.
- When renaming an API, complete the rename throughout the codebase instead of leaving compatibility aliases or other transitional shims unless explicitly requested.
- Keep the event system as simple as possible. Do not introduce new event types unless explicitly requested; prefer the existing events (e.g. `StateChanged`) to signal lifecycle changes.
- Write comments and docstrings only when they add information the code does not already convey. Do not restate what class names, field names, defaults, or config already make obvious; prefer no docstring over a redundant one.
