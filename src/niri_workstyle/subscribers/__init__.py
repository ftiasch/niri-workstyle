"""Explicit registration point for built-in workstyle subscribers."""

from niri_workstyle.core.subscriber import SubscriberRegistry
from niri_workstyle.subscribers.portrait_single_column import register as register_portrait_single_column
from niri_workstyle.subscribers.workspace_names import register as register_workspace_names


def register_builtin_subscribers(registry: SubscriberRegistry) -> None:
    """Register built-ins in deterministic action order."""
    register_workspace_names(registry)
    register_portrait_single_column(registry)
