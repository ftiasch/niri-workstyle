"""Race-tolerant in-memory state derived from the niri event stream."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import cast

from niri_workstyle.core.protocol import Event, JsonValue, Output, Window, WindowLayout, Workspace


@dataclass(frozen=True, slots=True)
class StateChange:
    """Policy-relevant effects of one state transition."""

    workspace_ids: frozenset[int] = frozenset()
    opened_window_id: int | None = None
    rename_workspaces: bool = False
    reconcile_layout: bool = False
    refresh_outputs: bool = False


@dataclass(slots=True)
class NiriState:
    """Current niri state, updated only from IPC events and Outputs responses."""

    workspaces: dict[int, Workspace] = field(default_factory=dict)
    windows: dict[int, Window] = field(default_factory=dict)
    outputs: dict[str, Output] = field(default_factory=dict)
    workspaces_initialized: bool = False
    windows_initialized: bool = False

    @property
    def ready(self) -> bool:
        """Return whether the initial workspace, window, and output state is available."""
        return self.workspaces_initialized and self.windows_initialized and bool(self.outputs)

    def replace_outputs(self, outputs: dict[str, Output]) -> None:
        """Replace the output snapshot returned by an Outputs request."""
        self.outputs = outputs

    def windows_on_workspace(self, workspace_id: int) -> list[Window]:
        """Return windows currently assigned to one workspace."""
        return [window for window in self.windows.values() if window["workspace_id"] == workspace_id]

    def apply(self, event: Event) -> StateChange:
        """Apply one event without assuming cross-event atomicity."""
        change = StateChange()
        match event.name:
            case "WorkspacesChanged":
                change = self._replace_workspaces(event.data)
            case "WindowsChanged":
                change = self._replace_windows(event.data)
            case "WindowOpenedOrChanged":
                change = self._update_window(event.data)
            case "WindowClosed":
                change = self._close_window(event.data)
            case "WindowFocusChanged":
                self._change_window_focus(event.data)
            case "WindowLayoutsChanged":
                change = self._change_window_layouts(event.data)
            case "WorkspaceActivated":
                change = self._activate_workspace(event.data)
            case "WorkspaceActiveWindowChanged":
                self._change_active_window(event.data)
            case "WorkspaceUrgencyChanged":
                self._change_workspace_urgency(event.data)
            case "WindowUrgencyChanged":
                self._change_window_urgency(event.data)
            case "ConfigLoaded":
                change = StateChange(
                    workspace_ids=frozenset(self.workspaces),
                    reconcile_layout=True,
                    refresh_outputs=True,
                )
        return change

    def _replace_workspaces(self, data: dict[str, JsonValue]) -> StateChange:
        old_ids = set(self.workspaces)
        workspaces = cast("list[Workspace]", data.get("workspaces", []))
        self.workspaces = {workspace["id"]: workspace for workspace in workspaces}
        self.workspaces_initialized = True
        unknown_output = any(
            workspace["output"] is not None and workspace["output"] not in self.outputs
            for workspace in self.workspaces.values()
        )
        return StateChange(
            workspace_ids=frozenset(old_ids | self.workspaces.keys()),
            reconcile_layout=self.windows_initialized,
            refresh_outputs=not self.outputs or unknown_output,
        )

    def _replace_windows(self, data: dict[str, JsonValue]) -> StateChange:
        old_workspace_ids = _window_workspace_ids(self.windows.values())
        windows = cast("list[Window]", data.get("windows", []))
        self.windows = {window["id"]: window for window in windows}
        self.windows_initialized = True
        workspace_ids = old_workspace_ids | _window_workspace_ids(windows)
        return StateChange(
            workspace_ids=frozenset(workspace_ids),
            rename_workspaces=True,
            reconcile_layout=True,
        )

    def _update_window(self, data: dict[str, JsonValue]) -> StateChange:
        window = cast("Window", data["window"])
        old_window = self.windows.get(window["id"])
        workspace_ids = _window_workspace_ids(item for item in (old_window, window) if item is not None)
        if window["is_focused"]:
            for current in self.windows.values():
                current["is_focused"] = False
        self.windows[window["id"]] = window
        return StateChange(
            workspace_ids=frozenset(workspace_ids),
            opened_window_id=window["id"] if old_window is None else None,
            rename_workspaces=True,
            reconcile_layout=True,
        )

    def _close_window(self, data: dict[str, JsonValue]) -> StateChange:
        window_id = cast("int", data["id"])
        window = self.windows.pop(window_id, None)
        workspace_ids = _window_workspace_ids([window] if window is not None else [])
        return StateChange(
            workspace_ids=frozenset(workspace_ids),
            rename_workspaces=window is not None,
            reconcile_layout=window is not None,
        )

    def _change_window_focus(self, data: dict[str, JsonValue]) -> None:
        focused_id = cast("int | None", data.get("id"))
        for window in self.windows.values():
            window["is_focused"] = window["id"] == focused_id

    def _change_window_layouts(self, data: dict[str, JsonValue]) -> StateChange:
        workspace_ids: set[int] = set()
        changes = cast("list[list[object]]", data.get("changes", []))
        for window_id_value, layout_value in changes:
            window_id = cast("int", window_id_value)
            window = self.windows.get(window_id)
            if window is None:
                continue
            window["layout"] = cast("WindowLayout", layout_value)
            if window["workspace_id"] is not None:
                workspace_ids.add(window["workspace_id"])
        return StateChange(workspace_ids=frozenset(workspace_ids), reconcile_layout=True)

    def _activate_workspace(self, data: dict[str, JsonValue]) -> StateChange:
        workspace_id = cast("int", data["id"])
        focused = cast("bool", data["focused"])
        activated = self.workspaces.get(workspace_id)
        if activated is None:
            return StateChange()
        output_name = activated["output"]
        for workspace in self.workspaces.values():
            if output_name is not None and workspace["output"] == output_name:
                workspace["is_active"] = workspace["id"] == workspace_id
            if focused:
                workspace["is_focused"] = workspace["id"] == workspace_id
        return StateChange(workspace_ids=frozenset({workspace_id}), reconcile_layout=True)

    def _change_active_window(self, data: dict[str, JsonValue]) -> None:
        workspace_id = cast("int", data["workspace_id"])
        workspace = self.workspaces.get(workspace_id)
        if workspace is not None:
            workspace["active_window_id"] = cast("int | None", data.get("active_window_id"))

    def _change_workspace_urgency(self, data: dict[str, JsonValue]) -> None:
        workspace = self.workspaces.get(cast("int", data["id"]))
        if workspace is not None:
            workspace["is_urgent"] = cast("bool", data["urgent"])

    def _change_window_urgency(self, data: dict[str, JsonValue]) -> None:
        window = self.windows.get(cast("int", data["id"]))
        if window is not None:
            window["is_urgent"] = cast("bool", data["urgent"])


def _window_workspace_ids(windows: Iterable[Window]) -> set[int]:
    return {window["workspace_id"] for window in windows if window["workspace_id"] is not None}
