# Agent Instructions

- Package `__init__.py` files that re-export symbols from sibling modules must use explicit relative imports, for example `from .module import PublicName`.
- Re-export only the intended public API from package `__init__.py` files. Keep implementation details private to their modules and list exported names in `__all__` when a package exposes a curated API.
