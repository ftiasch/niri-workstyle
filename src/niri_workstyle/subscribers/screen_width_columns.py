"""Keep the visible columns within one output width."""

from collections import defaultdict
from collections.abc import Iterable

from niri_workstyle.core.protocol import Action, Window
from niri_workstyle.core.state import NiriState, StateChange
from niri_workstyle.core.subscriber import SubscriberRegistry


class ScreenWidthColumnsSubscriber:
    """Stack overflowing windows into the last column that fits on screen."""

    name = "screen-width-columns"

    def notify(self, state: NiriState, change: StateChange) -> list[Action]:
        """Plan corrections only for relevant, fully initialized changes."""
        if not change.reconcile_layout or not state.ready:
            return []

        actions: list[Action] = []
        for workspace_id in sorted(change.workspace_ids):
            actions.extend(_plan_workspace(state, workspace_id))
        return actions


def _plan_workspace(state: NiriState, workspace_id: int) -> list[Action]:
    layout = _workspace_columns(state, workspace_id)
    if layout is None:
        return []
    output_width, columns = layout

    anchor_index = _last_fitting_column(columns, output_width)
    if anchor_index is None:
        return []
    anchor = min(columns[anchor_index], key=_window_position)
    return _consume_right_window(state.windows.values(), anchor, reset_scroll=anchor_index > 0)


def register(registry: SubscriberRegistry) -> None:
    """Actively register the screen-width column subscriber."""
    registry.register(ScreenWidthColumnsSubscriber())


def _workspace_columns(
    state: NiriState,
    workspace_id: int,
) -> tuple[int, list[list[Window]]] | None:
    workspace = state.workspaces.get(workspace_id)
    if workspace is None or workspace["output"] is None:
        return None
    output = state.outputs.get(workspace["output"])
    logical = output["logical"] if output is not None else None
    if logical is None:
        return None

    columns: defaultdict[int, list[Window]] = defaultdict(list)
    for window in state.windows_on_workspace(workspace_id):
        if window["is_floating"]:
            continue
        position = window["layout"]["pos_in_scrolling_layout"]
        if position is None:
            return None
        columns[position[0]].append(window)
    if not columns:
        return None
    return logical["width"], [columns[index] for index in sorted(columns)]


def _window_position(window: Window) -> tuple[int, int]:
    position = window["layout"]["pos_in_scrolling_layout"]
    return (position[1], window["id"]) if position is not None else (1_000_000, window["id"])


def _last_fitting_column(columns: list[list[Window]], output_width: int) -> int | None:
    total_width = _column_width(columns[0])
    for index, column in enumerate(columns[1:], start=1):
        total_width += _column_width(column)
        if total_width > output_width:
            return index - 1
    return None


def _column_width(windows: Iterable[Window]) -> float:
    return max(window["layout"]["tile_size"][0] for window in windows)


def _consume_right_window(
    windows: Iterable[Window],
    anchor: Window,
    *,
    reset_scroll: bool,
) -> list[Action]:
    focused_id = next((window["id"] for window in windows if window["is_focused"]), None)
    anchor_id = anchor["id"]
    actions: list[Action] = []
    if focused_id != anchor_id:
        actions.append(Action("FocusWindow", {"id": anchor_id}))
    actions.append(Action("ConsumeWindowIntoColumn"))

    # Consuming the rightmost column preserves niri's scrolling offset. Move
    # to the first column before restoring focus when multiple columns fit.
    if reset_scroll:
        actions.append(Action("FocusColumnFirst"))
    if focused_id is not None and (reset_scroll or focused_id != anchor_id):
        actions.append(Action("FocusWindow", {"id": focused_id}))
    return actions
