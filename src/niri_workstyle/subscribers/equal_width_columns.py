"""Keep tiled columns equally sized within one output width."""

from collections import defaultdict
from collections.abc import Iterable

from niri_workstyle.core.protocol import Action, JsonValue, Window
from niri_workstyle.core.state import NiriState, StateChange
from niri_workstyle.core.subscriber import SubscriberRegistry

WIDTH_TOLERANCE_PX = 4.0


class EqualWidthColumnsSubscriber:
    """Keep existing columns equal and stack newly opened windows at the end."""

    name = "equal-width-columns"

    def __init__(self) -> None:
        self._settled_column_counts: dict[int, int] = {}
        self._pending_opened_window_ids: set[int] = set()

    def notify(self, state: NiriState, change: StateChange) -> list[Action]:
        """Consume a new window first, then converge existing column widths."""
        if not change.reconcile_layout or not state.ready:
            return []

        if change.opened_window_id is not None:
            self._pending_opened_window_ids.add(change.opened_window_id)
        for window_id in sorted(self._pending_opened_window_ids):
            actions = _consume_opened_window(state, window_id)
            if actions is None:
                continue
            self._pending_opened_window_ids.remove(window_id)
            if actions:
                return actions

        actions: list[Action] = []
        for workspace_id in sorted(change.workspace_ids):
            layout = _workspace_layout(state, workspace_id)
            if layout is None:
                self._settled_column_counts.pop(workspace_id, None)
                continue

            output_width, columns = layout
            column_count = len(columns)
            column_count_changed = self._settled_column_counts.get(workspace_id) != column_count
            if column_count_changed:
                self._settled_column_counts.pop(workspace_id, None)

            width_actions = _equal_width_actions(output_width, columns)
            actions.extend(width_actions)
            if column_count_changed and not width_actions and state.workspaces[workspace_id]["is_active"]:
                actions.extend(_refocus_actions(state.windows.values(), columns))
                self._settled_column_counts[workspace_id] = column_count
        return actions


def register(registry: SubscriberRegistry) -> None:
    """Register the equal-width column subscriber."""
    registry.register(EqualWidthColumnsSubscriber())


def _workspace_layout(
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


def _consume_opened_window(state: NiriState, window_id: int) -> list[Action] | None:
    window = state.windows.get(window_id)
    if window is None or window["is_floating"]:
        return []
    if window["workspace_id"] is None:
        return None
    layout = _workspace_layout(state, window["workspace_id"])
    if layout is None:
        return None
    _, columns = layout

    opened_index = next(
        (index for index, column in enumerate(columns) if any(candidate["id"] == window_id for candidate in column)),
        None,
    )
    if opened_index is None:
        return None
    opened_column = columns[opened_index]
    if len(opened_column) != 1:
        rows = {_window_position(candidate)[0] for candidate in opened_column}
        return [] if len(rows) == len(opened_column) else None

    actions: list[Action] = []
    existing_columns = columns[:opened_index] + columns[opened_index + 1 :]
    if existing_columns:
        focused_id = _focused_window_id(state.windows.values())
        anchor_id = _column_anchor(existing_columns[-1])["id"]
        move_to_end = opened_index != len(columns) - 1
        reset_scroll = len(existing_columns) > 1

        if move_to_end:
            if focused_id != window_id:
                actions.append(Action("FocusWindow", {"id": window_id}))
            actions.append(Action("MoveColumnToLast"))
        if move_to_end or focused_id != anchor_id:
            actions.append(Action("FocusWindow", {"id": anchor_id}))
        actions.append(Action("ConsumeWindowIntoColumn"))
        if reset_scroll:
            actions.append(Action("FocusColumnFirst"))
        if focused_id is not None and (move_to_end or reset_scroll or focused_id != anchor_id):
            actions.append(Action("FocusWindow", {"id": focused_id}))
    return actions


def _equal_width_actions(output_width: int, columns: list[list[Window]]) -> list[Action]:
    column_count = len(columns)
    desired_width = output_width / column_count
    desired_percent = 100.0 / column_count
    actions: list[Action] = []
    for column in columns:
        if abs(_column_width(column) - desired_width) <= WIDTH_TOLERANCE_PX:
            continue
        anchor = _column_anchor(column)
        arguments: dict[str, JsonValue] = {
            "id": anchor["id"],
            "change": {"SetProportion": desired_percent},
        }
        actions.append(Action("SetWindowWidth", arguments))
    return actions


def _refocus_actions(windows: Iterable[Window], columns: list[list[Window]]) -> list[Action]:
    focused_id = _focused_window_id(windows)
    first_id = _column_anchor(columns[0])["id"]
    last_id = _column_anchor(columns[-1])["id"]
    actions: list[Action] = []
    if last_id != first_id:
        actions.append(Action("FocusWindow", {"id": last_id}))
    actions.extend(
        (
            Action("FocusWindow", {"id": first_id}),
            Action("CenterVisibleColumns"),
        )
    )
    if focused_id is not None and focused_id != first_id:
        actions.append(Action("FocusWindow", {"id": focused_id}))
    return actions


def _focused_window_id(windows: Iterable[Window]) -> int | None:
    return next((window["id"] for window in windows if window["is_focused"]), None)


def _column_anchor(windows: Iterable[Window]) -> Window:
    return min(windows, key=_window_position)


def _window_position(window: Window) -> tuple[int, int]:
    position = window["layout"]["pos_in_scrolling_layout"]
    return (position[1], window["id"]) if position is not None else (1_000_000, window["id"])


def _column_width(windows: Iterable[Window]) -> float:
    return max(window["layout"]["tile_size"][0] for window in windows)
