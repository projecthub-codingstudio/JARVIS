"""Simple stdio transport for the JARVIS application service."""

from __future__ import annotations

import sys

from jarvis.service.application import JarvisApplicationService
from jarvis.service.protocol import RpcRequest


def main() -> int:
    service = JarvisApplicationService()
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            request = RpcRequest.from_json(line)
            response = service.handle(request)
        except Exception as exc:
            sys.stdout.write(
                '{"request_id":"","session_id":"","ok":false,"payload":{},'
                f'"error":{{"code":"BAD_REQUEST","message":"{str(exc)}","retryable":false}}}}\n'
            )
            sys.stdout.flush()
            continue
        sys.stdout.write(response.to_json() + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
