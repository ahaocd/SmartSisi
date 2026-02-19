from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from typing import Optional, Tuple
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from websockets.legacy.client import connect as ws_connect
from websockets.legacy.server import WebSocketServerProtocol, serve

from gateway.app.auth import check_token
from gateway.app.control_codec import (
    build_control_ack,
    extract_control_type,
    is_control_payload,
)
from gateway.app.session_registry import SessionRegistry

LOG = logging.getLogger("sisi.gateway")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _query_first(path_query: str, key: str, default: str = "") -> str:
    query = parse_qs(path_query or "")
    values = query.get(key)
    if not values:
        return default
    return str(values[0]).strip() or default


class WsGatewayServer:
    def __init__(
        self,
        *,
        host: str = "0.0.0.0",
        port: int = 9102,
        media_backend_url: str = "ws://127.0.0.1:9002",
        control_backend_url: str = "ws://127.0.0.1:9003",
        access_token: str = "",
        max_message_bytes: int = 2 * 1024 * 1024,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.media_backend_url = media_backend_url.strip()
        self.control_backend_url = str(control_backend_url or "").strip()
        if not self.control_backend_url:
            raise ValueError("control backend url is required")
        self.access_token = access_token.strip()
        self.max_message_bytes = int(max_message_bytes)
        self.registry = SessionRegistry()
        self._stop_event: Optional[asyncio.Event] = None
        self._server = None

    async def run_forever(self) -> None:
        LOG.info(
            "[gateway] listening ws=%s:%s media_backend=%s control_backend=%s",
            self.host,
            self.port,
            self.media_backend_url,
            self.control_backend_url,
        )
        self._stop_event = asyncio.Event()
        async with serve(
            self._handle_client,
            self.host,
            self.port,
            max_size=self.max_message_bytes,
            ping_interval=15,
            ping_timeout=15,
        ) as server:
            self._server = server
            await self._stop_event.wait()
        self._server = None

    async def shutdown(self) -> None:
        stop_event = self._stop_event
        if stop_event is not None and not stop_event.is_set():
            stop_event.set()
        if self._server is not None:
            self._server.close()

    async def _handle_client(self, client: WebSocketServerProtocol, path: str) -> None:
        parsed = urlparse(path or "/")
        route = parsed.path or "/"

        ok, reason = check_token(parsed, client.request_headers, self.access_token)
        if not ok:
            await client.send(
                json.dumps(
                    {"type": "gateway_error", "reason": reason},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
            await client.close(code=1008, reason=reason)
            return

        if route == "/health":
            await client.send(json.dumps({"type": "health", "ok": True}))
            await client.close(code=1000, reason="ok")
            return
        if route == "/device":
            await self._handle_device(client, parsed)
            return
        if route == "/control":
            await self._handle_control(client, parsed)
            return

        await client.send(json.dumps({"type": "gateway_error", "reason": "unknown_route"}))
        await client.close(code=1008, reason="unknown_route")

    async def _handle_device(self, client: WebSocketServerProtocol, parsed) -> None:
        device_id = _query_first(parsed.query, "device_id", default="unknown_device")
        session_id = _query_first(parsed.query, "session_id", default=str(uuid4()))

        self.registry.open_session(session_id=session_id, device_id=device_id)
        LOG.info("[gateway] device_session_open session=%s device=%s", session_id, device_id)

        await client.send(
            json.dumps(
                {
                    "type": "gateway_session",
                    "session_id": session_id,
                    "device_id": device_id,
                    "ts_ms": _now_ms(),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )

        try:
            async with ws_connect(
                self.media_backend_url,
                max_size=self.max_message_bytes,
                ping_interval=15,
                ping_timeout=15,
            ) as backend:
                c2b = asyncio.create_task(self._pipe_client_to_backend(client, backend, session_id, device_id))
                b2c = asyncio.create_task(self._pipe_backend_to_client(backend, client, session_id))
                done, pending = await asyncio.wait(
                    {c2b, b2c},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for task in done:
                    exc = task.exception()
                    if exc:
                        LOG.warning("[gateway] device pipe ended with error: %s", str(exc))
        finally:
            self.registry.close_session(session_id)
            LOG.info("[gateway] device_session_close session=%s device=%s", session_id, device_id)

    async def _pipe_client_to_backend(
        self,
        client: WebSocketServerProtocol,
        backend,
        session_id: str,
        device_id: str,
    ) -> None:
        async for message in client:
            self.registry.touch(session_id)
            await backend.send(message)

            if isinstance(message, str) and is_control_payload(message):
                control_type = extract_control_type(message)
                ack = build_control_ack(
                    ok=True,
                    session_id=session_id,
                    device_id=device_id,
                    control_type=control_type,
                    ts_ms=_now_ms(),
                )
                await client.send(ack)

    async def _pipe_backend_to_client(self, backend, client: WebSocketServerProtocol, session_id: str) -> None:
        async for message in backend:
            self.registry.touch(session_id)
            await client.send(message)

    async def _handle_control(self, client: WebSocketServerProtocol, parsed) -> None:
        device_id = _query_first(parsed.query, "device_id", default="unknown_device")
        session_id = _query_first(parsed.query, "session_id", default=str(uuid4()))
        LOG.info("[gateway] control_lane_open session=%s device=%s", session_id, device_id)

        async for message in client:
            if not isinstance(message, str):
                ack = build_control_ack(
                    ok=False,
                    session_id=session_id,
                    device_id=device_id,
                    control_type="unknown",
                    reason="control_lane_text_only",
                    ts_ms=_now_ms(),
                )
                await client.send(ack)
                continue

            ok, reason = await self._forward_control(message)
            ack = build_control_ack(
                ok=ok,
                session_id=session_id,
                device_id=device_id,
                control_type=extract_control_type(message),
                reason=reason,
                ts_ms=_now_ms(),
            )
            await client.send(ack)

    async def _forward_control(self, payload: str) -> Tuple[bool, str]:
        try:
            async with ws_connect(
                self.control_backend_url,
                max_size=self.max_message_bytes,
                ping_interval=15,
                ping_timeout=15,
                open_timeout=5,
            ) as backend:
                await backend.send(payload)
            return True, ""
        except Exception as e:
            LOG.warning("[gateway] control forward failed backend=%s error=%s", self.control_backend_url, str(e))
            return False, f"forward_failed:{str(e)}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sisi app-layer websocket gateway")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9102)
    parser.add_argument("--media-backend", default="ws://127.0.0.1:9002")
    parser.add_argument("--control-backend", default="ws://127.0.0.1:9003")
    parser.add_argument("--access-token", default="")
    parser.add_argument("--max-message-bytes", type=int, default=2 * 1024 * 1024)
    parser.add_argument("--log-level", default="INFO")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    server = WsGatewayServer(
        host=args.host,
        port=args.port,
        media_backend_url=args.media_backend,
        control_backend_url=args.control_backend,
        access_token=args.access_token,
        max_message_bytes=args.max_message_bytes,
    )

    asyncio.run(server.run_forever())


if __name__ == "__main__":
    main()
