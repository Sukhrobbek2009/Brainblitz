"""Live WebSocket connections, grouped by room.

In-memory and per-process: it works with a single uvicorn worker. Running several
workers (or machines) would need a shared pub/sub such as Redis in front of this.
"""
import asyncio
from dataclasses import dataclass

from fastapi import WebSocket


@dataclass(eq=False)  # compare by identity so each connection is its own set member
class Connection:
    ws: WebSocket
    role: str  # "host" | "player"
    player_id: str | None = None


class RoomConnections:
    def __init__(self) -> None:
        self._rooms: dict[int, set[Connection]] = {}
        self._seen: dict[int, set[str]] = {}  # players who have connected to a room before

    def add(self, room_id: int, conn: Connection) -> None:
        self._rooms.setdefault(room_id, set()).add(conn)

    def remove(self, room_id: int, conn: Connection) -> None:
        conns = self._rooms.get(room_id)
        if conns is None:
            return
        conns.discard(conn)
        if not conns:
            del self._rooms[room_id]

    def has_connected_before(self, room_id: int, player_id: str) -> bool:
        return player_id in self._seen.get(room_id, ())

    def mark_connected(self, room_id: int, player_id: str) -> None:
        self._seen.setdefault(room_id, set()).add(player_id)

    def has_connection(self, room_id: int, player_id: str) -> bool:
        return any(c.player_id == player_id for c in self._rooms.get(room_id, ()))

    async def broadcast(
        self, room_id: int, message: dict, *, exclude: Connection | None = None, only_role: str | None = None
    ) -> None:
        targets = [
            c for c in self._rooms.get(room_id, ())
            if c is not exclude and (only_role is None or c.role == only_role)
        ]
        results = await asyncio.gather(
            *(c.ws.send_json(message) for c in targets), return_exceptions=True
        )
        for conn, result in zip(targets, results):
            if isinstance(result, Exception):  # socket already gone
                self.remove(room_id, conn)

    async def close_room(self, room_id: int, code: int = 1000, reason: str = "Game ended") -> None:
        """Close every socket in a room (after the final message went out) and forget it."""
        conns = list(self._rooms.pop(room_id, ()))
        self._seen.pop(room_id, None)
        await asyncio.gather(*(c.ws.close(code=code, reason=reason) for c in conns), return_exceptions=True)

    def broadcast_detached(self, room_id: int, message: dict) -> None:
        task = asyncio.get_running_loop().create_task(self.broadcast(room_id, message))
        _background.add(task)  # keep a reference until it finishes
        task.add_done_callback(_background.discard)


_background: set[asyncio.Task] = set()
connections = RoomConnections()
