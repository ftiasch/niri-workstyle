"""Command-line entry point for niri-workstyle."""

import argparse
import logging
from collections.abc import Sequence

from niri_workstyle.runtime.runner import run


def main(argv: Sequence[str] | None = None) -> int:
    """Run the workstyle daemon or one initial reconciliation."""
    parser = argparse.ArgumentParser(description="Apply local workspace and output policies through niri IPC")
    parser.add_argument("--socket", help="Override NIRI_SOCKET")
    parser.add_argument("--once", action="store_true", help="Process the initial event-stream snapshot and exit")
    parser.add_argument("--dry-run", action="store_true", help="Log planned actions without sending them")
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    arguments = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, arguments.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        run(socket_path=arguments.socket, once=arguments.once, dry_run=arguments.dry_run)
    except KeyboardInterrupt:
        return 130
    return 0
