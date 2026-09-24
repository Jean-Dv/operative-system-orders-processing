"""JSON-over-TCP protocol shared by the system and its clients."""

from __future__ import annotations

import json
import socket
from typing import Any


MAX_MESSAGE_BYTES = 16_384


class ProtocolError(ValueError):
    """Raised when a peer sends an invalid protocol message."""


def send_message(connection: socket.socket, message: dict[str, Any]) -> None:
    """Send one newline-delimited JSON object."""
    payload = json.dumps(message, separators=(",", ":")).encode("utf-8") + b"\n"
    connection.sendall(payload)


def receive_message(connection: socket.socket) -> dict[str, Any]:
    """Receive one size-limited, newline-delimited JSON object."""
    chunks = bytearray()
    while b"\n" not in chunks:
        chunk = connection.recv(4096)
        if not chunk:
            raise ProtocolError("connection closed before a complete message")
        chunks.extend(chunk)
        if len(chunks) > MAX_MESSAGE_BYTES:
            raise ProtocolError("message is too large")

    raw_message, _, _ = chunks.partition(b"\n")
    try:
        message = json.loads(raw_message)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProtocolError("message must be valid UTF-8 JSON") from error
    if not isinstance(message, dict):
        raise ProtocolError("message must be a JSON object")
    return message

