"""Workspace-name policy preserved from the original niri-workstyle script."""

from collections.abc import Iterable

from niri_workstyle.core.protocol import Action, JsonValue, Window
from niri_workstyle.core.state import NiriState, StateChange
from niri_workstyle.core.subscriber import SubscriberRegistry


class WorkspaceNamesSubscriber:
    """Update workspace labels when window metadata changes."""

    name = "workspace-names"

    def notify(self, state: NiriState, change: StateChange) -> Iterable[Action]:
        """Plan by-id renames only for window metadata changes."""
        if not change.rename_workspaces or not state.workspaces_initialized:
            return ()
        return _plan_workspace_names(state, change.workspace_ids)


def register(registry: SubscriberRegistry) -> None:
    """Actively register the workspace-name subscriber."""
    registry.register(WorkspaceNamesSubscriber())


def _plan_workspace_names(state: NiriState, workspace_ids: Iterable[int]) -> list[Action]:
    actions: list[Action] = []
    for workspace_id in sorted(set(workspace_ids)):
        workspace = state.workspaces.get(workspace_id)
        if workspace is None:
            continue
        labels = [window_label(window) for window in _sorted_windows(state.windows_on_workspace(workspace_id))]
        desired_name = f"{workspace_id}: {' / '.join(labels)}" if labels else str(workspace_id)
        if workspace["name"] == desired_name:
            continue
        arguments: dict[str, JsonValue] = {
            "name": desired_name,
            "workspace": {"Id": workspace_id},
        }
        actions.append(Action("SetWorkspaceName", arguments))
    return actions


def window_label(window: Window) -> str:
    """Format one optional-title IPC window for a workspace label."""
    title = window["title"] or window["app_id"] or f"window-{window['id']}"
    match window["app_id"]:
        case "code":
            return f"  [{title.removesuffix(' - Visual Studio Code')}]"
        case "google-chrome":
            return "Chrome"
        case "obsidian":
            return "Obsidian"
        case "kitty":
            return f"  [{title}]"
        case _:
            return title


def _sorted_windows(windows: Iterable[Window]) -> list[Window]:
    return sorted(windows, key=_window_sort_key)


def _window_sort_key(window: Window) -> tuple[int, int, int]:
    position = window["layout"]["pos_in_scrolling_layout"]
    if position is None:
        return (1_000_000, 1_000_000, window["id"])
    return (position[0], position[1], window["id"])
