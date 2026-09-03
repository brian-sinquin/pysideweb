"""Exercise real HTTP/WebSocket transport without starting a daemon server."""

import asyncio

import pytest
from aiohttp import WSMsgType, WSServerHandshakeError
from aiohttp.test_utils import TestClient, TestServer
from PySide6.QtWidgets import QPushButton

from pysideweb import server, state


def test_websocket_round_trip(monkeypatch):
    async def scenario():
        button = QPushButton('Before')
        button.clicked.connect(lambda: button.setText('After <&>'))
        button.show()
        async with TestClient(TestServer(server._create_app())) as client:
            monkeypatch.setattr(server, '_server_loop', asyncio.get_running_loop())
            origin = str(client.make_url('/')).rstrip('/')
            ws = await client.ws_connect('/ws', origin=origin)
            initial = await ws.receive_json(timeout=2)
            assert initial['roots'][0]['props']['text'] == 'Before'
            state.drain_changes()
            await ws.send_json({'id': button._wid, 'event': 'clicked'})
            update = await ws.receive_json(timeout=2)
            assert update['type'] == 'updates'
            assert any(c.get('value') == 'After <&>' for c in update['updates'])
            # An explicit resync must work even with no queued changes.
            await server._broadcast_tree(full_refresh=True)
            assert (await ws.receive_json(timeout=2))['type'] == 'full_tree'
            await ws.close()
        assert not server._clients
    asyncio.run(scenario())


def test_origin_and_host_checks(monkeypatch):
    monkeypatch.delenv('PYSIDEWEB_HOST', raising=False)

    async def scenario():
        async with TestClient(TestServer(server._create_app())) as client:
            for origin in ('https://evil.example', 'null'):
                with pytest.raises(WSServerHandshakeError) as error:
                    await client.ws_connect('/ws', origin=origin)
                assert error.value.status == 403
            response = await client.get('/', headers={'Host': 'rebind.example'})
            assert response.status == 403
            # Non-browser clients remain supported, not authenticated.
            ws = await client.ws_connect('/ws')
            assert (await ws.receive_json(timeout=2))['type'] == 'full_tree'
            await ws.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('payload', ['not json', '[]', '{"id": [], "event": "clicked"}',
                                     '{"id": "w1", "event": 4}', 'x' * (65 * 1024)])
def test_invalid_messages_close_connection(payload):
    async def scenario():
        async with TestClient(TestServer(server._create_app())) as client:
            ws = await client.ws_connect('/ws')
            await ws.receive_json(timeout=2)
            await ws.send_str(payload)
            message = await ws.receive(timeout=2)
            assert message.type == WSMsgType.CLOSE
            assert message.data in (1008, 1009)
    asyncio.run(scenario())


def test_live_rate_limit(monkeypatch):
    original = server.WebSocketValidator

    def limited():
        validator = original()
        validator.rate_limit_per_minute = 1
        return validator

    monkeypatch.setattr(server, 'WebSocketValidator', limited)

    async def scenario():
        async with TestClient(TestServer(server._create_app())) as client:
            ws = await client.ws_connect('/ws')
            await ws.receive_json(timeout=2)
            for _ in range(2):
                await ws.send_json({'id': 'missing', 'event': 'clicked'})
            assert (await ws.receive(timeout=2)).data == 1008
    asyncio.run(scenario())
