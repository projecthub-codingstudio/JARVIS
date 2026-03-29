"""Entry point for the JARVIS application service."""

from __future__ import annotations

import argparse
import os

from jarvis.service.socket_server import main as socket_main
from jarvis.service.stdio_server import main as stdio_main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="JARVIS application service")
    parser.add_argument(
        "--transport",
        choices=("stdio", "socket"),
        default=os.getenv("JARVIS_SERVICE_TRANSPORT", "stdio").strip().lower() or "stdio",
        help="Transport to run: stdio or socket",
    )
    args = parser.parse_args(argv)

    if args.transport == "socket":
        return socket_main()
    return stdio_main()


if __name__ == "__main__":
    raise SystemExit(main())
