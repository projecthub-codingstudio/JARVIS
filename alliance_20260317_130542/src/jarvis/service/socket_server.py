"""Unix domain socket transport for the JARVIS application service."""

from __future__ import annotations

import socket
import os
import threading
from pathlib import Path

from jarvis.service.application import JarvisApplicationService
from jarvis.service.protocol import RpcRequest
from jarvis.service.socket_path import resolve_socket_path


def _handle_client(client: socket.socket, service: JarvisApplicationService) -> None:
    with client:
        reader = client.makefile("r", encoding="utf-8", newline="\n")
        writer = client.makefile("w", encoding="utf-8", newline="\n")
        try:
            for line in reader:
                payload = line.strip()
                if not payload:
                    continue
                try:
                    request = RpcRequest.from_json(payload)
                    response = service.handle(request)
                except Exception as exc:
                    writer.write(
                        '{"request_id":"","session_id":"","ok":false,"payload":{},'
                        f'"error":{{"code":"BAD_REQUEST","message":"{str(exc)}","retryable":false}}}}\n'
                    )
                    writer.flush()
                    continue
                writer.write(response.to_json() + "\n")
                writer.flush()
        finally:
            reader.close()
            writer.close()


def main() -> int:
    service = JarvisApplicationService()
    socket_path = resolve_socket_path()
    pid_path = Path(f"{socket_path}.pid")
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        socket_path.unlink(missing_ok=True)
    except Exception:
        pass

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(socket_path))
        server.listen()
        try:
            pid_path.write_text(str(os.getpid()), encoding="utf-8")
        except Exception:
            pass
        while True:
            client, _ = server.accept()
            thread = threading.Thread(
                target=_handle_client,
                args=(client, service),
                daemon=True,
                name="jarvis-service-client",
            )
            thread.start()
    finally:
        server.close()
        try:
            socket_path.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            pid_path.unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
