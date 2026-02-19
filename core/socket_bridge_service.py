import asyncio
import socket
import threading
import time
import sys
import traceback

import websockets

__instances = {}


def _log(message, level=1):
    try:
        from utils import util

        util.log(level, f"[transport] {message}")
    except Exception:
        print(f"[transport] {message}")


def new_instance(
    ws_host='0.0.0.0',
    ws_port=9002,
    tcp_host='127.0.0.1',
    tcp_port=10001,
    *,
    instance_key='default',
    text_message_suffix=b'',
):
    key = str(instance_key or 'default')
    instance = __instances.get(key)
    if instance is None:
        instance = SocketBridgeService(
            ws_host=ws_host,
            ws_port=ws_port,
            tcp_host=tcp_host,
            tcp_port=tcp_port,
            text_message_suffix=text_message_suffix,
        )
        __instances[key] = instance
    return instance


def get_instance(instance_key='default'):
    key = str(instance_key or 'default')
    return __instances.get(key)


def remove_instance(instance_key='default'):
    key = str(instance_key or 'default')
    return __instances.pop(key, None)


class SocketBridgeService:
    def __init__(
        self,
        ws_host='0.0.0.0',
        ws_port=9002,
        tcp_host='127.0.0.1',
        tcp_port=10001,
        text_message_suffix=b'',
    ):
        self.ws_host = ws_host
        self.ws_port = ws_port
        self.tcp_host = tcp_host
        self.tcp_port = tcp_port
        self.text_message_suffix = bytes(text_message_suffix or b'')

        self.websockets = {}
        self.sockets = {}
        self.traffic = {}
        self.message_queue = asyncio.Queue()
        self.running = True
        self.loop = None
        self.tasks = set()
        self.server = None

    async def handler(self, websocket, path=None):
        ws_id = id(websocket)
        self.websockets[ws_id] = websocket
        self.traffic[ws_id] = {
            "up_bytes": 0,
            "up_msgs": 0,
            "down_bytes": 0,
            "down_msgs": 0,
            "last_report_ms": int(time.time() * 1000),
        }
        remote_addr = getattr(websocket, "remote_address", None)
        _log(f"ws bridge client connected ws_id={ws_id} remote={remote_addr}")
        try:
            if ws_id not in self.sockets:
                sock = await self.create_socket_client()
                if sock:
                    self.sockets[ws_id] = sock
                else:
                    print(f"Failed to connect TCP socket for WebSocket {ws_id}")
                    await websocket.close()
                    return

            receive_task = asyncio.create_task(self.receive_from_socket(ws_id))
            self.tasks.add(receive_task)
            receive_task.add_done_callback(self.tasks.discard)

            async for message in websocket:
                await self.send_to_socket(ws_id, message)
        except websockets.ConnectionClosed as e:
            _log(f"ws bridge client closed ws_id={ws_id} remote={remote_addr} reason={str(e)}")
        except Exception as e:
            _log(f"ws bridge client error ws_id={ws_id} remote={remote_addr} error={str(e)}", level=2)
        finally:
            self.close_socket_client(ws_id)
            self.websockets.pop(ws_id, None)
            self.traffic.pop(ws_id, None)
            _log(f"ws bridge client disconnected ws_id={ws_id} remote={remote_addr}")

    async def create_socket_client(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect((self.tcp_host, self.tcp_port))
            sock.setblocking(True)
            return sock
        except Exception as e:
            _log(
                f"ws bridge tcp connect failed target={self.tcp_host}:{self.tcp_port} error={str(e)}",
                level=2,
            )
            return None

    async def send_to_socket(self, ws_id, message):
        sock = self.sockets.get(ws_id)
        if not sock:
            return
        try:
            if isinstance(message, str):
                message = message.encode('utf-8')
                if self.text_message_suffix:
                    message = message + self.text_message_suffix
            await asyncio.to_thread(sock.sendall, message)
            self._record_traffic(ws_id, uplink_bytes=len(message), uplink_msgs=1)
        except Exception:
            self.close_socket_client(ws_id)

    async def receive_from_socket(self, ws_id):
        sock = self.sockets.get(ws_id)
        if not sock:
            return
        try:
            while self.running:
                data = await asyncio.to_thread(sock.recv, 4096)
                if data:
                    self._record_traffic(ws_id, downlink_bytes=len(data), downlink_msgs=1)
                    await self.message_queue.put((ws_id, data))
                else:
                    break
        except Exception:
            pass
        finally:
            self.close_socket_client(ws_id)

    async def process_message_queue(self):
        while self.running or not self.message_queue.empty():
            try:
                ws_id, data = await asyncio.wait_for(self.message_queue.get(), timeout=1.0)
                websocket = self.websockets.get(ws_id)
                if websocket and getattr(websocket, 'open', True):
                    try:
                        await websocket.send(data)
                    except Exception:
                        pass
                self.message_queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception:
                pass

    def close_socket_client(self, ws_id):
        sock = self.sockets.pop(ws_id, None)
        if not sock:
            return
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        sock.close()

    async def start(self, host=None, port=None):
        if host is not None:
            self.ws_host = host
        if port is not None:
            self.ws_port = port

        self.running = True
        # Disable aggressive ping timeout on unstable local Wi-Fi/OEM stacks to avoid false disconnect.
        self.server = await websockets.serve(
            self.handler,
            self.ws_host,
            self.ws_port,
            ping_interval=None,
            max_size=None,
        )
        _log(
            f"ws bridge listening ws={self.ws_host}:{self.ws_port} -> tcp={self.tcp_host}:{self.tcp_port}",
            level=1,
        )

        process_task = asyncio.create_task(self.process_message_queue())
        self.tasks.add(process_task)
        process_task.add_done_callback(self.tasks.discard)

        try:
            await self.server.wait_closed()
        except asyncio.CancelledError:
            pass
        finally:
            await self.shutdown()

    async def shutdown(self):
        if not self.running:
            return
        self.running = False

        for _, ws in list(self.websockets.items()):
            try:
                await ws.close()
            except Exception:
                pass
        self.websockets.clear()

        for _, sock in list(self.sockets.items()):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            sock.close()
        self.sockets.clear()

        await self.message_queue.join()

        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()

        if self.server:
            self.server.close()
            await self.server.wait_closed()

    def start_service(self, host=None, port=None, tcp_host=None, tcp_port=None):
        if host is not None:
            self.ws_host = host
        if port is not None:
            self.ws_port = port
        if tcp_host is not None:
            self.tcp_host = tcp_host
        if tcp_port is not None:
            self.tcp_port = tcp_port

        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.start())
        except Exception as e:
            _log(
                f"ws bridge start failed ws={self.ws_host}:{self.ws_port} -> tcp={self.tcp_host}:{self.tcp_port} error={str(e)}",
                level=2,
            )
            _log(traceback.format_exc(), level=2)
        finally:
            self.loop.close()
            self.loop = None

    def stop_server(self):
        if self.loop and self.loop.is_running():
            try:
                future = asyncio.run_coroutine_threadsafe(self.shutdown(), self.loop)
                future.result(timeout=5)
            except Exception as e:
                _log(f"ws bridge stop failed: {str(e)}", level=2)

    def _record_traffic(self, ws_id, uplink_bytes=0, uplink_msgs=0, downlink_bytes=0, downlink_msgs=0):
        stat = self.traffic.get(ws_id)
        if not stat:
            return
        stat["up_bytes"] += max(0, int(uplink_bytes))
        stat["up_msgs"] += max(0, int(uplink_msgs))
        stat["down_bytes"] += max(0, int(downlink_bytes))
        stat["down_msgs"] += max(0, int(downlink_msgs))
        now_ms = int(time.time() * 1000)
        if (now_ms - stat["last_report_ms"]) >= 5000:
            _log(
                "ws bridge traffic ws_id={} up_bytes={} up_msgs={} down_bytes={} down_msgs={}".format(
                    ws_id,
                    stat["up_bytes"],
                    stat["up_msgs"],
                    stat["down_bytes"],
                    stat["down_msgs"],
                ),
                level=1,
            )
            stat["up_bytes"] = 0
            stat["up_msgs"] = 0
            stat["down_bytes"] = 0
            stat["down_msgs"] = 0
            stat["last_report_ms"] = now_ms


if __name__ == '__main__':
    service = new_instance()
    service_thread = threading.Thread(target=service.start_service, daemon=True)
    service_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print('Initiating shutdown...')
        if service.loop and service.loop.is_running():
            future = asyncio.run_coroutine_threadsafe(service.shutdown(), service.loop)
            try:
                future.result()
                print('Shutdown coroutine completed.')
            except Exception as e:
                print(f'Shutdown exception: {e}', file=sys.stderr)
        service_thread.join()
        print('Service has been shut down.')
