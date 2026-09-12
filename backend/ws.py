"""WebSocket connection registry.

Authenticated on connect (backend/routes/runs.py does the handshake check
before accepting), and broadcasts are per-run so one run's decisions cannot
leak into another run's socket.
"""

import json

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self._conns: dict[int, set[WebSocket]] = {}

    async def connect(self, run_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self._conns.setdefault(run_id, set()).add(ws)

    def disconnect(self, run_id: int, ws: WebSocket) -> None:
        conns = self._conns.get(run_id)
        if conns is not None:
            conns.discard(ws)
            if not conns:
                del self._conns[run_id]

    async def broadcast(self, run_id: int, message: dict) -> None:
        conns = self._conns.get(run_id)
        if not conns:
            return
        payload = json.dumps(message)
        dead = []
        for ws in conns:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(run_id, ws)
