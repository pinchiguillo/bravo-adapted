#!/usr/bin/env python3
"""
Smoke test: full job chat flow, including WebSocket streaming.

Flow: create announcement and job -> send a REST message -> upload and attach
an asset -> fetch history -> connect to the job WebSocket -> send a message ->
observe the streamed event.

Usage:
  python3 scripts/e2e/smoke_job_chat_full_flow.py
  python3 scripts/e2e/smoke_job_chat_full_flow.py --url <base_url> [--announcement-uuid <uuid>]
"""

import argparse
import base64
import hashlib
import json
import os
import socket
import ssl
import struct
from datetime import datetime
from urllib.parse import quote, urlparse

from smoke_job_chat_attachments import (
    SAMPLE_PDF,
    create_job,
    register_user,
    run_full_scenario,
    send_message,
    setup_announcement,
)


def log(msg, ok=True):
    icon = "✅" if ok else "❌"
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {icon} {msg}")


def fail(msg):
    log(msg, ok=False)
    raise SystemExit(1)


class SimpleWebSocketClient:
    """Minimal RFC6455 client for dependency-free gateway smoke tests."""

    GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def __init__(self, websocket_url: str, timeout: float = 5.0):
        self.websocket_url = websocket_url
        self.timeout = timeout
        self.sock = None

    def connect(self):
        parsed = urlparse(self.websocket_url)
        host = parsed.hostname
        if not host:
            raise RuntimeError(f"Invalid websocket URL: {self.websocket_url}")
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        raw_sock = socket.create_connection((host, port), timeout=self.timeout)
        raw_sock.settimeout(self.timeout)
        if parsed.scheme == "wss":
            context = ssl.create_default_context()
            self.sock = context.wrap_socket(raw_sock, server_hostname=host)
        else:
            self.sock = raw_sock

        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Origin: {'https' if parsed.scheme == 'wss' else 'http'}://{host}\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self.sock.sendall(request.encode("ascii"))

        response = self._read_http_response()
        status_line = response.split("\r\n", 1)[0]
        if " 101 " not in status_line:
            raise RuntimeError(f"WebSocket handshake failed: {status_line}")

        expected_accept = base64.b64encode(hashlib.sha1(f"{key}{self.GUID}".encode("ascii")).digest()).decode("ascii")
        if f"Sec-WebSocket-Accept: {expected_accept}" not in response:
            raise RuntimeError("WebSocket handshake missing valid Sec-WebSocket-Accept header")

    def close(self):
        if self.sock is None:
            return
        try:
            self._send_frame(0x8, b"")
        except OSError:
            pass
        try:
            self.sock.close()
        finally:
            self.sock = None

    def send_json(self, payload: dict):
        data = json.dumps(payload).encode("utf-8")
        self._send_frame(0x1, data)

    def recv_json(self):
        while True:
            opcode, payload = self._recv_frame()
            if opcode == 0x1:
                return json.loads(payload.decode("utf-8"))
            if opcode == 0x8:
                raise RuntimeError("WebSocket closed by server")
            if opcode == 0x9:
                self._send_frame(0xA, payload)

    def _read_http_response(self):
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            data += chunk
        return data.decode("latin1", errors="replace")

    def _send_frame(self, opcode: int, payload: bytes):
        if self.sock is None:
            raise RuntimeError("WebSocket is not connected")

        first_byte = 0x80 | opcode
        mask_key = os.urandom(4)
        length = len(payload)
        if length < 126:
            header = bytes([first_byte, 0x80 | length])
        elif length < 65536:
            header = bytes([first_byte, 0x80 | 126]) + struct.pack("!H", length)
        else:
            header = bytes([first_byte, 0x80 | 127]) + struct.pack("!Q", length)

        masked = bytes(payload[i] ^ mask_key[i % 4] for i in range(length))
        self.sock.sendall(header + mask_key + masked)

    def _recv_frame(self):
        if self.sock is None:
            raise RuntimeError("WebSocket is not connected")

        header = self._recv_exact(2)
        first_byte, second_byte = header[0], header[1]
        opcode = first_byte & 0x0F
        masked = bool(second_byte & 0x80)
        length = second_byte & 0x7F

        if length == 126:
            length = struct.unpack("!H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8))[0]

        mask_key = self._recv_exact(4) if masked else b""
        payload = self._recv_exact(length) if length else b""
        if masked:
            payload = bytes(payload[i] ^ mask_key[i % 4] for i in range(length))
        return opcode, payload

    def _recv_exact(self, size: int):
        data = b""
        while len(data) < size:
            chunk = self.sock.recv(size - len(data))
            if not chunk:
                raise RuntimeError("Unexpected EOF while reading WebSocket frame")
            data += chunk
        return data


def build_websocket_url(base_url: str, job_uuid: str, token: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme == "https":
        scheme = "wss"
    elif parsed.scheme == "http":
        scheme = "ws"
    else:
        raise RuntimeError(f"Unsupported base URL scheme: {parsed.scheme}")
    return f"{scheme}://{parsed.netloc}/ws/jobs/{job_uuid}/chat/?token={quote(token)}"


def test_websocket_streaming(base_url: str, token: str, job_uuid: str):
    print(f"\n{'─' * 60}")
    print("  Validation: websocket streaming should deliver new chat messages")
    print(f"{'─' * 60}")

    ws_url = build_websocket_url(base_url, job_uuid, token)
    client = SimpleWebSocketClient(ws_url, timeout=8.0)
    try:
        client.connect()
        log(f"WebSocket connected: {ws_url}")

        expected_content = f"WS smoke message {datetime.now().isoformat()}"
        client.send_json({"type": "message", "content": expected_content})

        deadline = datetime.now().timestamp() + 8.0
        while datetime.now().timestamp() < deadline:
            event = client.recv_json()
            event_type = event.get("type")
            if event_type != "message":
                continue
            payload = event.get("data", {})
            if payload.get("content") == expected_content:
                log("WebSocket message broadcast received")
                return

        fail("WebSocket connected but did not stream the sent chat message")
    except Exception as exc:
        fail(f"WebSocket job chat streaming failed: {exc}")
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description="External E2E test for full Job Chat flow")
    parser.add_argument("--url", default="http://localhost:24356", help="Base URL of the API gateway")
    parser.add_argument("--token", default=None, help="Existing JWT access token (skips registration)")
    parser.add_argument(
        "--announcement-uuid",
        default=None,
        metavar="UUID",
        help="UUID of a pre-existing approved announcement for remote gateway mode.",
    )
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    print("=" * 60)
    print(f"  Full Job Chat Flow Tests  →  {base_url}")
    print("=" * 60)

    token = args.token or register_user(base_url)
    announcement_uuid = setup_announcement(base_url, token, args.announcement_uuid)

    run_full_scenario(
        base_url,
        token,
        "REST attachment flow",
        SAMPLE_PDF,
        "document.pdf",
        "application/pdf",
        announcement_uuid,
    )

    job_uuid = create_job(base_url, token, announcement_uuid)
    message_uuid = send_message(base_url, token, job_uuid)
    log(f"REST baseline message created: {message_uuid}")
    test_websocket_streaming(base_url, token, job_uuid)

    print("\n" + "=" * 60)
    log("Full job chat flow test passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
