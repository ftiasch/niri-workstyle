"""One-column policy for every portrait output."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar

from niri_workstyle.core.protocol import Action, JsonValue, Window
from niri_workstyle.core.state import NiriState, StateChange
from niri_workstyle.core.subscriber import SubscriberRegistry


@dataclass(frozen=True, slots=True)
class PortraitSingleColumnSubscriber:
    """Keep tiled windows in one full-width column on portrait outputs."""

    name: ClassVar[str] = "portrait-single-column"
    width_percent: float = 100.0
    full_width_tolerance_px: float = 32.0

    def notify(self, state: NiriState, change: StateChange) -> Iterable[Action]:
        """Plan layout corrections only for relevant, fully initialized changes."""
        if not change.reconcile_layout or not state.ready:
            return ()
        return self._plan(state, change.workspace_ids)

    def _plan(self, state: NiriState, workspace_ids: Iterable[int]) -> list[Action]:
        actions: list[Action] = []
        for workspace_id in sorted(set(workspace_ids)):
            actions.extend(self._plan_workspace(state, workspace_id))
        return actions

    def _plan_workspace(self, state: NiriState, workspace_id: int) -> list[Action]:
        portrait_layout = _portrait_workspace_layout(state, workspace_id)
        if portrait_layout is None:
            return []
        output_width, columns = portrait_layout

        first_column = min(columns)
        if len(columns) > 1:
            return _append_next_column(columns, first_column)

        anchor = columns[first_column][0]
        if anchor["layout"]["tile_size"][0] >= output_width - self.full_width_tolerance_px:
            return []
        arguments: dict[str, JsonValue] = {
            "id": anchor["id"],
            "change": {"SetProportion": self.width_percent},
        }
        return [Action("SetWindowWidth", arguments)]


def register(registry: SubscriberRegistry) -> None:
    """Actively register the portrait single-column subscriber."""
    registry.register(PortraitSingleColumnSubscriber())


def _portrait_workspace_layout(
    state: NiriState,
    workspace_id: int,
) -> tuple[int, dict[int, list[Window]]] | None:
    workspace = state.workspaces.get(workspace_id)
    if workspace is None or workspace["output"] is None:
        return None
    output = state.outputs.get(workspace["output"])
    if output is None:
        return None
    logical = output["logical"]
    if logical is None or logical["height"] <= logical["width"]:
        return None
    columns = _tiled_columns(state.windows_on_workspace(workspace_id))
    if not columns:
        return None
    return logical["width"], columns


def _tiled_columns(windows: Iterable[Window]) -> dict[int, list[Window]]:
    columns: defaultdict[int, list[Window]] = defaultdict(list)
    for window in windows:
        if window["is_floating"]:
            continue
        position = window["layout"]["pos_in_scrolling_layout"]
        if position is None:
            return {}
        columns[position[0]].append(window)
    for column_windows in columns.values():
        column_windows.sort(key=_window_position)
    return dict(columns)


def _window_position(window: Window) -> tuple[int, int]:
    position = window["layout"]["pos_in_scrolling_layout"]
    return (position[1], window["id"]) if position is not None else (1_000_000, window["id"])


def _append_next_column(columns: dict[int, list[Window]], first_column: int) -> list[Action]:
    focused = next(
        (window for column in columns.values() for window in column if window["is_focused"]),
        None,
    )
    if focused is None:
        return []

    focused_position = focused["layout"]["pos_in_scrolling_layout"]
    anchor = (
        focused if focused_position is not None and focused_position[0] == first_column else columns[first_column][0]
    )
    if anchor["id"] == focused["id"]:
        return [Action("ConsumeWindowIntoColumn")]

    # Niri appends the right-hand window to the bottom of the focused column.
    # Restore the user's focus after the focused-only consume action.
    return [
        Action("FocusWindow", {"id": anchor["id"]}),
        Action("ConsumeWindowIntoColumn"),
        Action("FocusWindow", {"id": focused["id"]}),
    ]
