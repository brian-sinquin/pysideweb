"""
pysideweb.server — aiohttp web server with WebSocket hub.

Runs in a daemon thread, serves the SPA frontend via HTTP, and maintains
a WebSocket connection for real-time bidirectional sync of the widget tree.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from . import state
from .security import SafeJSONEncoder
from .websocket_validator import WebSocketValidator

if TYPE_CHECKING:
    from aiohttp import web
else:
    # Imported lazily on the server thread (see _run_server) -- `import aiohttp`
    # costs ~300 ms and we don't want that on the main thread at startup.
    web = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------

_server_thread: threading.Thread | None = None
_server_loop: asyncio.AbstractEventLoop | None = None
_server_started = threading.Event()
_server_error: str | None = None
_start_lock = threading.Lock()
_clients: set[_Client] = set()
_static_dir = Path(__file__).parent / "static"

_MAX_PENDING_MESSAGES = 8
_MAX_PENDING_BYTES = 8 * 1024 * 1024
_SEND_TIMEOUT = 5.0
_CLOSE_TIMEOUT = 2.0


class _Client:
    """Loop-owned outbox. Overflow replaces stale deltas with a fresh snapshot."""

    def __init__(self, ws, transport=None):
        self.ws = ws
        self.transport = transport
        self.pending: deque[tuple[str, int] | None] = deque()
        self.pending_bytes = 0
        self.resync_pending = False
        self.closed = False
        self._close_task = None
        self.ready = asyncio.Event()
        self.writer = asyncio.create_task(self._write(), name="pysideweb-writer")

    def _clear(self):
        self.pending.clear()
        self.pending_bytes = 0
        self.resync_pending = False

    def enqueue(self, message: str, full_refresh: bool = False):
        if self.closed:
            return
        if full_refresh:
            self._clear()
        elif self.resync_pending:
            return  # the snapshot is built later, after the blocked send finishes
        size = len(message.encode("utf-8"))
        if len(self.pending) >= _MAX_PENDING_MESSAGES or self.pending_bytes + size > _MAX_PENDING_BYTES:
            self._clear()
            self.pending.append(None)
            self.resync_pending = True
        else:
            self.pending.append((message, size))
            self.pending_bytes += size
        self.ready.set()

    async def _write(self):
        close_code = 1000
        try:
            while True:
                await self.ready.wait()
                while self.pending:
                    entry = self.pending.popleft()
                    if entry is None:
                        self.resync_pending = False
                        message = state.full_tree_json()
                        if len(message.encode("utf-8")) > _MAX_PENDING_BYTES:
                            close_code = 1009
                            return
                    else:
                        message, size = entry
                        self.pending_bytes -= size
                    await asyncio.wait_for(self.ws.send_str(message), timeout=_SEND_TIMEOUT)
                self.ready.clear()
        except asyncio.CancelledError:
            raise
        except Exception:
            close_code = 1011
        finally:
            self.closed = True
            self._clear()
            await self._close_socket(close_code)

    async def _close_socket(self, code=1000):
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._finish_close(code))
        await asyncio.shield(self._close_task)

    async def _finish_close(self, code):
        try:
            await asyncio.wait_for(self.ws.close(code=code), timeout=_CLOSE_TIMEOUT)
        except Exception:
            if self.transport is not None:
                self.transport.close()
        finally:
            _clients.discard(self)

    async def close(self):
        self.closed = True
        self.writer.cancel()
        await asyncio.gather(self.writer, return_exceptions=True)
        self._clear()
        await self._close_socket()


async def _close_clients(app):
    await asyncio.gather(*(client.close() for client in tuple(_clients)))


# ---------------------------------------------------------------------------
# WebSocket handler
# ---------------------------------------------------------------------------

async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    origin = request.headers.get("Origin")
    if origin is not None and origin != f"{request.scheme}://{request.host}":
        raise web.HTTPForbidden(text="WebSocket origin must match the application")
    validator = WebSocketValidator()
    ws = web.WebSocketResponse(heartbeat=30.0, max_msg_size=64 * 1024)
    await ws.prepare(request)

    client = _Client(ws, request.transport)
    _clients.add(client)
    print(f"[PySideWeb] Browser connected ({len(_clients)} client(s))")

    try:
        client.enqueue(state.full_tree_json(), full_refresh=True)
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    valid, reason = validator.validate_message("connection", msg.data)
                    if not valid:
                        await ws.close(code=1008, message=reason.encode())
                        break
                    event = json.loads(msg.data)
                    if not validator.validate_event(event):
                        await ws.close(code=1008, message=b"Invalid event")
                        break
                    state.dispatch_event(event)
                    # Event handlers share the state-change broadcast debounce.
                    _schedule_broadcast()
                except (json.JSONDecodeError, RecursionError):
                    await ws.close(code=1008, message=b"Invalid JSON")
                    break
                except Exception as e:
                    print(f"[PySideWeb] Event error: {e}")
            elif msg.type == web.WSMsgType.ERROR:
                print(f"[PySideWeb] WebSocket error: {ws.exception()}")
    finally:
        await client.close()
        print(f"[PySideWeb] Browser disconnected ({len(_clients)} client(s))")

    return ws


# ---------------------------------------------------------------------------
# Broadcast (debounced)
# ---------------------------------------------------------------------------

_broadcast_scheduled = False
_BROADCAST_INTERVAL = 0.05  # 50ms debounce → max 20 updates/sec


async def _broadcast_tree(full_refresh: bool = False):
    """Send widget tree updates or the full tree to all connected clients."""
    global _broadcast_scheduled
    _broadcast_scheduled = False

    if not _clients:
        # Drain changes anyway so they don't pile up
        state.drain_changes()
        return

    changes = state.drain_changes()
    if not changes and not full_refresh:
        return

    # Check if a full refresh is requested in any queued changes
    has_full_refresh = full_refresh or any(c.get("type") == "full_refresh" for c in changes)

    if has_full_refresh:
        msg_json = state.full_tree_json()
    else:
        # Send incremental updates
        msg_json = json.dumps({
            "type": "updates",
            "updates": [c for c in changes if c.get("type") == "update"]
        }, cls=SafeJSONEncoder)

    # Serialization is shared; socket I/O happens only in independent writers.
    for client in tuple(_clients):
        client.enqueue(msg_json, full_refresh=has_full_refresh)


def _schedule_broadcast():
    """Marshal debounce decisions to the server loop, avoiding cross-thread races."""
    loop = _server_loop
    if loop is not None and not loop.is_closed():
        loop.call_soon_threadsafe(_schedule_on_loop)


def _schedule_on_loop():
    global _broadcast_scheduled
    if not _broadcast_scheduled:
        _broadcast_scheduled = True
        asyncio.create_task(_delayed_broadcast())


async def _delayed_broadcast():
    """Wait for the debounce interval, then broadcast."""
    await asyncio.sleep(_BROADCAST_INTERVAL)
    await _broadcast_tree()


def _on_state_change():
    """Called from state module when widget properties change."""
    if _server_loop and _clients:
        _schedule_broadcast()


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------

async def index_handler(request: web.Request) -> web.Response:
    resp = web.FileResponse(_static_dir / "index.html")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


async def _no_cache_static(request, handler):
    """The renderer/CSS are edited in place during development and the app is
    long-running; without this the browser serves a stale renderer.js/style.css
    after an update until a hard reload."""
    # Reject DNS-rebinding hostnames when bound to loopback. Wider bindings
    # explicitly opt into network access and still enforce WebSocket Origin.
    bind_host = os.environ.get("PYSIDEWEB_HOST", "127.0.0.1")
    if bind_host in {"127.0.0.1", "localhost", "::1"}:
        try:
            hostname = urlsplit("//" + request.host).hostname
        except ValueError:
            hostname = None
        if hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise web.HTTPForbidden(text="Unrecognized loopback host")
    resp = await handler(request)
    if request.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
    return resp


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def _create_app():
    global web
    if web is None:
        from aiohttp import web
    app = web.Application(middlewares=[web.middleware(_no_cache_static)])
    app.on_shutdown.append(_close_clients)
    app.router.add_get("/ws", websocket_handler)
    app.router.add_get("/", index_handler)
    app.router.add_static("/static/", path=str(_static_dir), name="static")
    return app


# ---------------------------------------------------------------------------
# Server thread
# ---------------------------------------------------------------------------

def _run_server(port: int):
    global _server_loop, _server_error, web

    # Defaults to loopback-only: the WebSocket endpoint has no authentication,
    # so anything reachable can inspect and drive the app's widget tree.
    # PYSIDEWEB_HOST opts into wider exposure (e.g. "0.0.0.0").
    host = os.environ.get("PYSIDEWEB_HOST", "127.0.0.1")
    try:
        from aiohttp import web as _web  # ~300 ms; kept off the main thread
        web = _web
        _server_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_server_loop)
        app = _create_app()
        runner = web.AppRunner(app)
        _server_loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, host, port)
        _server_loop.run_until_complete(site.start())
    except OSError as e:
        _server_error = (
            f"could not bind {host}:{port} ({e.strerror or e}). "
            f"Another PySideWeb app is probably already running — stop it, or "
            f"set PYSIDEWEB_PORT to a free port."
        )
        _server_started.set()  # unblock the waiter immediately; no 10s hang
        return
    except Exception as e:  # noqa: BLE001 - report anything, don't hang
        _server_error = f"server failed to start: {e!r}"
        _server_started.set()
        return

    _server_started.set()
    state.add_change_listener(_on_state_change)
    _server_loop.run_forever()


def start_server(port: int = 8765) -> None:
    """Start the web-server daemon thread if it isn't already running.
    Non-blocking — importing aiohttp (~300 ms) and binding happen on the
    thread, so a caller can kick this off early and overlap it with other
    startup work, then `wait_for_server()` when it actually needs the server."""
    global _server_thread, _server_error
    with _start_lock:
        if _server_thread is not None and _server_thread.is_alive():
            return
        _server_error = None
        _server_started.clear()
        _server_thread = threading.Thread(
            target=_run_server, args=(port,), daemon=True, name="pysideweb-server",
        )
        _server_thread.start()


def wait_for_server(timeout: float = 8.0) -> bool:
    """Block until the server is listening (or failed). Returns True on success."""
    _server_started.wait(timeout=timeout)
    if _server_error is not None:
        print(f"[PySideWeb] {_server_error}")
        return False
    if not _server_started.is_set():
        print(f"[PySideWeb] WARNING: server did not start within {timeout:.0f}s")
        return False
    return True


def ensure_server_running(port: int = 8765) -> bool:
    """Back-compat: start + wait."""
    start_server(port)
    return wait_for_server()
