# Agent Instructions

- Package `__init__.py` files that re-export symbols from sibling modules must use explicit relative imports, for example `from .module import PublicName`.
- Otherwise, prefer absolute imports from the `agent` package, for example `from agent.events import EventBus`.
- Re-export only the intended public API from package `__init__.py` files. Define `__all__` only in package `__init__.py` files; never add it to regular modules. Mark module-private implementation details with a leading underscore.
- Do not give a symbol a leading underscore when it is imported by another module. Leading underscores are reserved for implementation details used only within their defining module.
- Do not add `from __future__ import annotations` defensively by default; the project targets Python 3.14, so only use it when a concrete compatibility reason requires it.
- Avoid defensive `getattr` probing for known APIs. Prefer concrete types, typed protocols, or explicit branches over duck-typed fallback logic unless the code genuinely supports multiple external shapes.
- Use dataclasses only for classes that are primarily data containers. Prefer regular classes when a class owns significant behavior or validation logic.
- Keep class attributes and instance variables private by default. Expose public attributes only when they are intentionally part of the public API.
- Prefer private module-level helper functions for module-local or cross-module logic instead of static methods that do not need class state.
- Do not inline factory or constructor calls as arguments to another operation. Assign the created object to a descriptive local variable first, especially before passing it to a repository or service call.
- When renaming an API, complete the rename throughout the codebase instead of leaving compatibility aliases or other transitional shims unless explicitly requested.

## Tests

Do not automatically add unit tests for every change.

Add tests only when they protect meaningful behavior:
- regressions
- domain rules
- edge cases
- public contracts

Avoid:
- tests for implementation details
- excessive mocking
- tests for simple data containers
- duplicating type-system guarantees

Always run the smallest relevant existing test suite.
