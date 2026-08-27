"""Explicit registration point for built-in workstyle subscribers."""

from niri_workstyle.core.subscriber import SubscriberRegistry
from niri_workstyle.subscribers import screen_width_columns


def register_builtin_subscribers(registry: SubscriberRegistry) -> None:
    """Register built-ins in deterministic action order."""
    screen_width_columns.register(registry)
