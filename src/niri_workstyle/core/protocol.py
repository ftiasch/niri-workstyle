"""Typed subset of the niri 26.04 IPC protocol used by this project."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict

type JsonScalar = bool | int | float | str | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


class WindowLayout(TypedDict):
    """Position and size fields reported for a niri window."""

    pos_in_scrolling_layout: list[int] | None
    tile_size: list[float]
    window_size: list[int]
    tile_pos_in_workspace_view: list[float] | None
    window_offset_in_tile: list[float]


class Window(TypedDict):
    """Window fields reported by niri 26.04."""

    id: int
    title: str | None
    app_id: str | None
    pid: int | None
    workspace_id: int | None
    is_focused: bool
    is_floating: bool
    is_urgent: bool
    layout: WindowLayout
    focus_timestamp: dict[str, int] | None


class Workspace(TypedDict):
    """Workspace fields reported by niri 26.04."""

    id: int
    idx: int
    name: str | None
    output: str | None
    is_urgent: bool
    is_active: bool
    is_focused: bool
    active_window_id: int | None


class LogicalOutput(TypedDict):
    """Logical geometry of an enabled output."""

    x: int
    y: int
    width: int
    height: int
    scale: float
    transform: str


class Output(TypedDict):
    """Output identity and geometry fields reported by niri 26.04."""

    name: str
    make: str
    model: str
    serial: str | None
    physical_size: list[int] | None
    modes: list[dict[str, JsonValue]]
    current_mode: int | None
    is_custom_mode: bool
    vrr_supported: bool
    vrr_enabled: bool
    logical: LogicalOutput | None


@dataclass(frozen=True, slots=True)
class Event:
    """One externally tagged niri event."""

    name: str
    data: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class Action:
    """One externally tagged niri action."""

    name: str
    arguments: dict[str, JsonValue] = field(default_factory=dict)

    def request(self) -> dict[str, JsonValue]:
        """Encode this action as a niri IPC request."""
        return {"Action": {self.name: self.arguments}}
