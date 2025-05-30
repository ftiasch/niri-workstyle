import json
import logging
import os
import subprocess
from typing import TypedDict

import coloredlogs


class Window(TypedDict):
    app_id: str
    id: int
    is_floating: bool
    is_focused: bool
    is_urgent: bool
    pid: int
    title: str
    workspace_id: int


def stringify(win: Window):
    logger.debug("stringify %s", win)
    match win["app_id"]:
        case "code":
            # strip the suffix "- Visual Studio Code" from the title
            return "  [" + win["title"][: -len("- Visual Studio Code")] + "]"
        case "google-chrome":
            return "Chrome"
        case "obsidian":
            return "Obsidian"
        case "kitty":
            return "  [" + win["title"] + "]"
        case _:
            return win["title"]


class Core:
    __workspaces: dict[int, set[int]]
    __wins = dict[int, Window]

    def __init__(self):
        self.__workspaces = {}
        self.__wins = {}

    def process(self, line):
        msg = json.loads(line)
        logger.info("msg %s", msg)
        for event_name, event in msg.items():
            match event_name:
                case "WorkspacesChanged":
                    ws_ids = [ws["id"] for ws in event.get("workspaces", [])]
                    closed_ws = set(self.__workspaces.keys()) - set(ws_ids)
                    logger.debug("closed workspaces: %s", closed_ws)
                    for ws_id in closed_ws:
                        del self.__workspaces[ws_id]
                    opened_ws = set(ws_ids) - set(self.__workspaces.keys())
                    logger.debug("opened workspaces: %s", opened_ws)
                    for ws_id in opened_ws:
                        self.__workspaces[ws_id] = set()
                case "WindowOpenedOrChanged":
                    win = event["window"]
                    self.__update_win(win)
                case "WindowsChanged":
                    for win in event["windows"]:
                        self.__update_win(win)
                case "WindowClosed":
                    win_id = event["id"]
                    win = self.__wins.pop(win_id, None)
                    if win:
                        ws_id = win["workspace_id"]
                        logger.info(
                            "Window closed: id=%d (title=%r) from workspace=%d",
                            win_id,
                            win["title"],
                            ws_id,
                        )
                        self.__workspaces[ws_id].remove(win_id)
                        self.__update_ws_name(ws_id)
                    else:
                        logger.warning("Tried to close unknown window: id=%d", win_id)
        logger.debug("workspaces: %s", self.__workspaces.items())

    def __update_ws_name(self, ws_id):
        new_name_parts = [
            stringify(self.__wins[win_id]) for win_id in self.__workspaces[ws_id]
        ]
        if new_name_parts:
            new_name = str(ws_id) + ": " + " / ".join(new_name_parts)
        else:
            new_name = str(ws_id)
        logger.info('rename workspace %d to "%s"', ws_id, new_name)
        subprocess.check_call(
            [
                "niri",
                "msg",
                "action",
                "set-workspace-name",
                new_name,
                "--workspace",
                str(ws_id),
            ],
        )

    def __update_win(self, win):
        win_id = win["id"]
        new_ws_id = win["workspace_id"]
        if win_id in self.__wins:
            old_ws_id = self.__wins[win_id]["workspace_id"]
            if old_ws_id != new_ws_id:
                logger.info(
                    "Window moved: id=%d (title=%r) from workspace=%d to workspace=%d",
                    win_id,
                    win["title"],
                    old_ws_id,
                    new_ws_id,
                )
                self.__workspaces[old_ws_id].remove(win_id)
                self.__update_ws_name(old_ws_id)
        else:
            logger.info(
                "Window opened: id=%d (title=%r) in workspace=%d",
                win_id,
                win["title"],
                new_ws_id,
            )
        self.__wins[win_id] = win
        self.__workspaces[new_ws_id].add(win_id)
        self.__update_ws_name(new_ws_id)


def main():
    while True:
        process = subprocess.Popen(
            ["niri", "msg", "--json", "event-stream"],
            stdout=subprocess.PIPE,
            text=True,
        )

        core = Core()
        try:
            for line in process.stdout:
                core.process(line)
        finally:
            logger.exception("Error processing line: %s", line)
            process.wait()
            logger.info(
                "Process exited with code %d. Respawning...", process.returncode
            )


if __name__ == "__main__":
    coloredlogs.install(level=os.environ.get("LOG_LEVEL", "INFO"))
    logger = logging.getLogger(__name__)
    main()
