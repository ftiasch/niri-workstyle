"""Subscriber contract and explicit registry for event-driven policies."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol

from niri_workstyle.core.protocol import Action
from niri_workstyle.core.state import NiriState, StateChange


class Subscriber(Protocol):
    """A detachable consumer of reduced niri state changes."""

    @property
    def name(self) -> str:
        """Return the subscriber's unique registry name."""
        ...

    def notify(self, state: NiriState, change: StateChange) -> Iterable[Action]:
        """Return actions for one reduced state change."""
        ...


@dataclass(slots=True)
class SubscriberRegistry:
    """Ordered subscriber collection with duplicate-name protection."""

    _subscribers: list[Subscriber] = field(default_factory=list)

    def register(self, subscriber: Subscriber) -> None:
        """Register one subscriber in action execution order."""
        if any(current.name == subscriber.name for current in self._subscribers):
            message = f"subscriber already registered: {subscriber.name}"
            raise ValueError(message)
        self._subscribers.append(subscriber)

    def notify(self, state: NiriState, change: StateChange) -> list[Action]:
        """Collect actions from all subscribers in registration order."""
        return [action for subscriber in self._subscribers for action in subscriber.notify(state, change)]

    @property
    def names(self) -> tuple[str, ...]:
        """Return registered names for logs and diagnostics."""
        return tuple(subscriber.name for subscriber in self._subscribers)
