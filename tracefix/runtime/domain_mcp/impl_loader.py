"""Load and invoke local domain-tool implementations from a workspace ``tools_impl.py``.

``impl: local`` tools declared in PlusCal (`[tool: name(...); impl: local]`) are
generated into ``tools.json`` (schemas) + a ``tools_impl.py`` stub the user fills.
This loader binds those Python functions so the domain MCP server (and any other
caller) can execute a tool by name with keyword args. Pure-Python, no ``mcp`` and
no SDK dependency, so it imports anywhere and is unit-testable offline.
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from typing import Any, Callable


class DomainImpls:
    """The callables found in a workspace ``tools_impl.py``, addressed by tool name."""

    def __init__(self, fns: dict[str, Callable[..., Any]]):
        self._fns = fns

    @property
    def names(self) -> list[str]:
        return list(self._fns)

    def has(self, name: str) -> bool:
        return name in self._fns

    def call(self, name: str, arguments: dict | None = None) -> Any:
        """Invoke ``name`` with keyword ``arguments``; return its (JSON-able) result.

        Raises KeyError if no such impl, TypeError on a bad signature match — both
        surfaced to the caller (the MCP server serializes them as an error result so
        the agent can react), never silently swallowed."""
        fn = self._fns.get(name)
        if fn is None:
            raise KeyError(f"no local impl for tool {name!r} in tools_impl.py")
        return fn(**(arguments or {}))


def load_impls(impl_path: str | Path) -> DomainImpls:
    """Import ``tools_impl.py`` as an isolated module and collect its public functions.

    Module-level ``def``s whose name does not start with ``_`` become tools. The file
    is loaded under a unique module name so repeated loads (e.g. per agent) don't clash
    in ``sys.modules``."""
    path = Path(impl_path)
    if not path.exists():
        raise FileNotFoundError(f"tools_impl.py not found: {path}")
    spec = importlib.util.spec_from_file_location(f"tracefix_tools_impl_{abs(hash(str(path)))}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fns = {
        name: obj
        for name, obj in vars(module).items()
        if not name.startswith("_") and inspect.isfunction(obj)
        and obj.__module__ == module.__name__
    }
    return DomainImpls(fns)
