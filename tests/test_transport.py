"""Deterministic outbox pressure tests; real wire tests live in test_server."""

import asyncio
import json

import pytest

from pysideweb import server, state


class Socket:
    def __init__(self, blocked=False):
        self.gate = asyncio.Event()
        if not blocked:
            self.gate.set()
        self.started = asyncio.Event()
        self.messages = asyncio.Queue()
        self.close_codes = []

    async def send_str(self, message):
        self.started.set()
        await self.gate.wait()
        self.messages.put_nowait(message)

    async def close(self, code):
        self.close_codes.append(code)


async def receive(socket):
    return await asyncio.wait_for(socket.messages.get(), timeout=1)


def test_slow_client_does_not_block_broadcast_and_resyncs(monkeypatch):
    async def scenario():
        slow, fast = Socket(blocked=True), Socket()
        clients = [server._Client(slow), server._Client(fast)]
        monkeypatch.setattr(server, '_clients', set(clients))
        latest = 0
        monkeypatch.setattr(state, 'drain_changes', lambda: [
            {'type': 'update', 'id': 'w1', 'prop': 'text', 'value': latest},
        ])
        monkeypatch.setattr(state, 'full_tree_json', lambda: json.dumps({
            'type': 'full_tree', 'latest': latest,
        }))
        try:
            clients[0].enqueue('initial')
            await asyncio.wait_for(slow.started.wait(), timeout=1)
            for latest in range(100):
                await server._broadcast_tree()
                assert json.loads(await receive(fast))['updates'][0]['value'] == latest
                assert len(clients[0].pending) <= server._MAX_PENDING_MESSAGES
                assert clients[0].pending_bytes <= server._MAX_PENDING_BYTES
            assert clients[0].resync_pending
            slow.gate.set()
            assert await receive(slow) == 'initial'
            assert json.loads(await receive(slow)) == {'type': 'full_tree', 'latest': 99}
            assert slow.messages.empty()
        finally:
            await server._close_clients(None)
        assert not server._clients
        assert all(client.writer.done() for client in clients)

    asyncio.run(scenario())


def test_byte_limit_counts_utf8_and_builds_one_lazy_snapshot(monkeypatch):
    monkeypatch.setattr(server, '_MAX_PENDING_BYTES', 8)
    monkeypatch.setattr(state, 'full_tree_json', lambda: 'current')

    async def scenario():
        socket = Socket()
        client = server._Client(socket)
        try:
            client.enqueue('é' * 4)
            assert client.pending_bytes == 8
            client.enqueue('x')
            client.enqueue('ignored stale delta')
            assert list(client.pending) == [None]
            assert client.pending_bytes == 0
            assert await receive(socket) == 'current'
        finally:
            await client.close()

    asyncio.run(scenario())


def test_full_refresh_supersedes_pending_deltas():
    async def scenario():
        socket = Socket()
        client = server._Client(socket)
        try:
            client.enqueue('stale')
            client.enqueue('snapshot', full_refresh=True)
            client.enqueue('new delta')
            assert await receive(socket) == 'snapshot'
            assert await receive(socket) == 'new delta'
        finally:
            await client.close()

    asyncio.run(scenario())


@pytest.mark.parametrize('oversized', [False, True])
def test_stalled_send_or_oversized_snapshot_closes_client(monkeypatch, oversized):
    monkeypatch.setattr(server, '_SEND_TIMEOUT', 0.01)
    monkeypatch.setattr(server, '_MAX_PENDING_BYTES', 8)
    monkeypatch.setattr(state, 'full_tree_json', lambda: 'x' * 9)

    async def scenario():
        socket = Socket(blocked=True)
        client = server._Client(socket)
        monkeypatch.setattr(server, '_clients', {client})
        client.enqueue('x' * (9 if oversized else 1))
        await asyncio.wait_for(client.writer, timeout=1)
        assert socket.close_codes == [1009 if oversized else 1011]
        assert client.closed and not client.pending and client.pending_bytes == 0
        assert not server._clients
        client.enqueue('ignored')
        await client.close()
        assert len(socket.close_codes) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize('start_writer', [False, True])
def test_close_cleans_up_even_before_writer_starts(monkeypatch, start_writer):
    async def scenario():
        socket = Socket(blocked=True)
        client = server._Client(socket)
        monkeypatch.setattr(server, '_clients', {client})
        client.enqueue('pending')
        if start_writer:
            await asyncio.wait_for(socket.started.wait(), timeout=1)
        await client.close()
        await client.close()
        assert socket.close_codes == [1000]
        assert client.writer.done() and client._close_task.done()
        assert not client.pending and not server._clients

    asyncio.run(scenario())


@pytest.mark.parametrize('hang', [False, True])
def test_failed_socket_close_releases_transport(monkeypatch, hang):
    monkeypatch.setattr(server, '_CLOSE_TIMEOUT', 0.01)

    class BrokenSocket(Socket):
        async def close(self, code):
            if hang:
                await asyncio.Event().wait()
            raise OSError('connection lost')

    class Transport:
        closed = False

        def close(self):
            self.closed = True

    async def scenario():
        transport = Transport()
        client = server._Client(BrokenSocket(), transport)
        await asyncio.wait_for(client.close(), timeout=1)
        assert transport.closed

    asyncio.run(scenario())
