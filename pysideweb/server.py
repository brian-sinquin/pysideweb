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

from aiohttp import web

from . import state

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------

_server_thread: threading.Thread | None = None
_server_loop: asyncio.AbstractEventLoop | None = None
_server_started = threading.Event()
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
                    # After event dispatch, send updated tree
                    await _broadcast_tree()
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
    index_path = _static_dir / "index.html"
    return web.FileResponse(index_path)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def _create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/ws", websocket_handler)
    app.router.add_get("/", index_handler)
    # Serve static files
    app.router.add_static("/static/", path=str(_static_dir), name="static")
    return app


# ---------------------------------------------------------------------------
# Server thread
# ---------------------------------------------------------------------------

def _run_server(port: int):
    global _server_loop

    _server_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_server_loop)

    app = _create_app()
    runner = web.AppRunner(app)
    _server_loop.run_until_complete(runner.setup())

    # Defaults to loopback-only: the WebSocket endpoint has no authentication,
    # so anything reachable can inspect and drive the app's widget tree.
    # Binding "0.0.0.0" unconditionally would expose that to the whole LAN
    # by default. PYSIDEWEB_HOST opts into wider exposure explicitly (e.g.
    # "0.0.0.0" to reach the app from another device on the network).
    host = os.environ.get("PYSIDEWEB_HOST", "127.0.0.1")
    site = web.TCPSite(runner, host, port)
    _server_loop.run_until_complete(site.start())

    _server_started.set()

    # Register state change listener
    state.add_change_listener(_on_state_change)

    # Run forever
    _server_loop.run_forever()


def ensure_server_running(port: int = 8765):
    """Start the web server in a daemon thread if not already running."""
    global _server_thread

    if _server_thread is not None and _server_thread.is_alive():
        return

    _server_thread = threading.Thread(
        target=_run_server,
        args=(port,),
        daemon=True,
        name="pysideweb-server",
    )
    _server_thread.start()

    # Wait for the server to be ready
    _server_started.wait(timeout=10.0)
    if not _server_started.is_set():
        print("[PySideWeb] WARNING: Server did not start within 10 seconds")
