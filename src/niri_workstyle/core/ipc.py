"""Blocking Unix-socket client for niri's line-delimited JSON IPC."""

from __future__ import annotations

import json
import os
import socket
from collections.abc import Iterator
from types import TracebackType
from typing import TextIO, cast

from niri_workstyle.core.protocol import Action, Event, JsonValue, Output


class NiriIPCError(RuntimeError):
    """Base error for niri IPC failures."""


class NiriConnectionError(NiriIPCError):
    """The niri socket disconnected or returned malformed data."""


class NiriReplyError(NiriIPCError):
    """Niri rejected a valid IPC request."""


class NiriConnection:
    """One request/reply connection to a niri Unix socket."""

    def __init__(self, socket_path: str) -> None:
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._socket.connect(socket_path)
        self._reader: TextIO = self._socket.makefile("r", encoding="utf-8")
        self._writer: TextIO = self._socket.makefile("w", encoding="utf-8")
        self._closed = False

    @classmethod
    def from_environment(cls) -> NiriConnection:
        """Connect using the socket exported by the current niri session."""
        try:
            socket_path = os.environ["NIRI_SOCKET"]
        except KeyError as error:
            message = "NIRI_SOCKET is not set"
            raise NiriConnectionError(message) from error
        return cls(socket_path)

    def __enter__(self) -> NiriConnection:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close this connection. Calling close more than once is safe."""
        if self._closed:
            return
        self._closed = True
        self._writer.close()
        self._reader.close()
        self._socket.close()

    def request(self, request: JsonValue) -> JsonValue:
        """Send one request and return the successful response payload."""
        self._writer.write(json.dumps(request, separators=(",", ":")))
        self._writer.write("\n")
        self._writer.flush()

        line = self._reader.readline()
        if not line:
            message = "niri closed the IPC connection"
            raise NiriConnectionError(message)

        reply = _parse_object(line)
        if "Err" in reply:
            raise NiriReplyError(str(reply["Err"]))
        if "Ok" not in reply:
            message = f"invalid niri reply: {reply!r}"
            raise NiriConnectionError(message)
        return reply["Ok"]

    def action(self, action: Action) -> JsonValue:
        """Execute one action."""
        return self.request(action.request())

    def outputs(self) -> dict[str, Output]:
        """Return the currently connected outputs keyed by connector name."""
        response = self.request("Outputs")
        if not isinstance(response, dict) or not isinstance(response.get("Outputs"), dict):
            message = f"invalid Outputs response: {response!r}"
            raise NiriConnectionError(message)
        return cast("dict[str, Output]", response["Outputs"])

    def event_stream(self) -> Iterator[Event]:
        """Yield events after switching this connection into event-stream mode."""
        acknowledgement = self.request("EventStream")
        if acknowledgement != "Handled":
            message = f"invalid EventStream acknowledgement: {acknowledgement!r}"
            raise NiriConnectionError(message)

        for line in self._reader:
            message = _parse_object(line)
            if len(message) != 1:
                error = f"invalid niri event: {message!r}"
                raise NiriConnectionError(error)
            name, data = next(iter(message.items()))
            if not isinstance(data, dict):
                error = f"invalid {name} event payload: {data!r}"
                raise NiriConnectionError(error)
            yield Event(name=name, data=data)


def _parse_object(line: str) -> dict[str, JsonValue]:
    try:
        value = json.loads(line)
    except json.JSONDecodeError as error:
        message = f"invalid JSON from niri: {line.rstrip()!r}"
        raise NiriConnectionError(message) from error
    if not isinstance(value, dict):
        message = f"expected a JSON object from niri, got {value!r}"
        raise NiriConnectionError(message)
    return cast("dict[str, JsonValue]", value)
