"""Generic event loop for explicitly registered subscribers."""

import logging
from dataclasses import replace

from niri_workstyle.core.ipc import NiriConnection, NiriReplyError
from niri_workstyle.core.protocol import Action
from niri_workstyle.core.state import NiriState
from niri_workstyle.core.subscriber import SubscriberRegistry
from niri_workstyle.subscribers import register_builtin_subscribers

LOGGER = logging.getLogger(__name__)


def run(*, socket_path: str | None = None, once: bool = False, dry_run: bool = False) -> None:
    """Consume the niri event stream and apply convergent policies."""
    with _connect(socket_path) as commands, _connect(socket_path) as events:
        state = NiriState()
        registry = SubscriberRegistry()
        register_builtin_subscribers(registry)
        LOGGER.info("registered subscribers: %s", ", ".join(registry.names))
        for event in events.event_stream():
            change = state.apply(event)
            if change.refresh_outputs:
                state.replace_outputs(commands.outputs())
                change = replace(
                    change,
                    workspace_ids=frozenset(state.workspaces),
                    reconcile_layout=True,
                )

            actions = registry.notify(state, change)
            _execute_actions(commands, actions, dry_run=dry_run)
            if once and state.ready:
                return


def _connect(socket_path: str | None) -> NiriConnection:
    return NiriConnection(socket_path) if socket_path is not None else NiriConnection.from_environment()


def _execute_actions(commands: NiriConnection, actions: list[Action], *, dry_run: bool) -> None:
    for action in actions:
        LOGGER.info("niri action %s %s", action.name, action.arguments)
        if dry_run:
            continue
        try:
            commands.action(action)
        except NiriReplyError:
            LOGGER.warning("niri rejected action %s %s", action.name, action.arguments, exc_info=True)
