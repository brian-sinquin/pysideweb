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
from pathlib import Path
from typing import TYPE_CHECKING

from . import state

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
_clients: set[web.WebSocketResponse] = set()
_static_dir = Path(__file__).parent / "static"


# ---------------------------------------------------------------------------
# WebSocket handler
# ---------------------------------------------------------------------------

async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse(heartbeat=30.0)
    await ws.prepare(request)

    _clients.add(ws)
    print(f"[PySideWeb] Browser connected ({len(_clients)} client(s))")

    # Send full tree on connect
    try:
        tree_json = state.full_tree_json()
        await ws.send_str(tree_json)
    except Exception as e:
        print(f"[PySideWeb] Error sending initial tree: {e}")

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    event = json.loads(msg.data)
                    state.dispatch_event(event)
                    # dispatch_event's signal handlers call state.notify_* which
                    # pokes the listener -> a debounced broadcast is scheduled.
                    # (Previously this sent a full tree synchronously per event,
                    # so a browser-driven slider drag round-tripped the whole
                    # tree once per pixel.) Nudge the scheduler in case the
                    # handler changed nothing observable but we still want to
                    # confirm state to the client.
                    _schedule_broadcast()
                except json.JSONDecodeError:
                    pass
                except Exception as e:
                    print(f"[PySideWeb] Event error: {e}")
            elif msg.type == web.WSMsgType.ERROR:
                print(f"[PySideWeb] WebSocket error: {ws.exception()}")
    finally:
        _clients.discard(ws)
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
    if not changes:
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
        })

    dead: list[web.WebSocketResponse] = []
    for ws in list(_clients):
        try:
            await ws.send_str(msg_json)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _clients.discard(ws)


def _schedule_broadcast():
    """Schedule a broadcast if one isn't already pending."""
    global _broadcast_scheduled
    if _broadcast_scheduled:
        return
    _broadcast_scheduled = True
    if _server_loop:
        _server_loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(_delayed_broadcast())
        )


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
    resp = await handler(request)
    if request.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
    return resp


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def _create_app():
    app = web.Application(middlewares=[web.middleware(_no_cache_static)])
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
