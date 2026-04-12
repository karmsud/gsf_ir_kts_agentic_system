"""
ToolRegistry — Manages available tools per agent with access control.
Implements the @agent_tool decorator for registration.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolMetadata:
    """Metadata for a registered tool."""
    name: str
    description: str
    function: Callable
    allowed_agents: list[str]
    parameters: dict[str, type] = field(default_factory=dict)


class ToolAccessDenied(Exception):
    """Raised when an agent tries to use a tool it doesn't have access to."""
    def __init__(self, tool_name: str, agent_name: str):
        super().__init__(
            f"Agent '{agent_name}' does not have access to tool '{tool_name}'"
        )
        self.tool_name = tool_name
        self.agent_name = agent_name


class ToolRegistry:
    """
    Manages available tools per agent.

    Tools are registered with an allowlist of agent names.
    When an agent invokes a tool, the registry checks the allowlist.

    Usage:
        registry = ToolRegistry()

        @agent_tool(name="vector_search", agents=["qa", "model_creation"], registry=registry)
        def vector_search(query: str) -> list[dict]:
            ...

        # Agent invocation
        results = registry.invoke("vector_search", "qa", query="overcollateralization")
    """

    def __init__(self):
        self._tools: dict[str, ToolMetadata] = {}

    def register(self, tool_fn: Callable, metadata: ToolMetadata) -> None:
        """Register a tool function with metadata."""
        metadata.function = tool_fn
        self._tools[metadata.name] = metadata

    def get_tools(self, agent_name: str) -> list[ToolMetadata]:
        """Get all tools available to a specific agent."""
        return [
            meta for meta in self._tools.values()
            if agent_name in meta.allowed_agents or "*" in meta.allowed_agents
        ]

    def get_tool(self, tool_name: str) -> ToolMetadata | None:
        """Get a tool by name."""
        return self._tools.get(tool_name)

    def invoke(self, tool_name: str, agent_name: str, **kwargs) -> Any:
        """
        Invoke a tool on behalf of an agent.

        Raises:
            ToolAccessDenied: if agent is not in the tool's allowlist
            KeyError: if tool_name not found
        """
        if tool_name not in self._tools:
            raise KeyError(f"Tool '{tool_name}' not found in registry")

        meta = self._tools[tool_name]
        if agent_name not in meta.allowed_agents and "*" not in meta.allowed_agents:
            raise ToolAccessDenied(tool_name, agent_name)

        return meta.function(**kwargs)

    def list_tool_names(self) -> list[str]:
        """Return all registered tool names."""
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __repr__(self) -> str:
        return f"ToolRegistry({len(self._tools)} tools)"


# Global registry instance
_global_registry = ToolRegistry()


def get_global_registry() -> ToolRegistry:
    """Get the global tool registry."""
    return _global_registry


def agent_tool(
    name: str,
    agents: list[str],
    description: str = "",
    registry: ToolRegistry | None = None,
) -> Callable:
    """
    Decorator to register a function as an agent tool.

    Args:
        name: Tool name for the registry
        agents: List of agent names that can access this tool. Use ["*"] for all.
        description: Human-readable description
        registry: Optional specific registry (defaults to global)

    Usage:
        @agent_tool(name="vector_search", agents=["qa", "model_creation"])
        def vector_search(query: str, deal_scope: DealScope) -> list[dict]:
            ...
    """
    target_registry = registry or _global_registry

    def decorator(func: Callable) -> Callable:
        metadata = ToolMetadata(
            name=name,
            description=description or func.__doc__ or "",
            function=func,
            allowed_agents=agents,
        )
        target_registry.register(func, metadata)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        wrapper._tool_metadata = metadata  # type: ignore
        return wrapper

    return decorator
