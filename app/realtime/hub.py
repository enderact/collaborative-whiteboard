"""Cross-instance event fanout over Redis Pub/Sub.

The important rule here is that there is exactly one delivery path. A handler
never writes straight to its own local sockets; it publishes to Redis and every
instance, including the one that published, delivers from its subscription. The
naive alternative (write locally *and* publish) makes each stroke arrive twice on
the originating server, which is the bug this design exists to avoid.

Presence and cursor positions live only in Redis with a TTL. They are worthless
after a disconnect, so persisting them to MongoDB would be write amplification
for no benefit — the split between the two stores is deliberate.
"""

import asyncio
import contextlib
import json
import logging
from collections import defaultdict

from fastapi import WebSocket

from app.config import settings
from app.db import redis

log = logging.getLogger("whiteboard.hub")

CHANNEL_PREFIX = "wb:room:"
PRESENCE_TTL = 30  # seconds


def channel(room_code: str) -> str:
    return f"{CHANNEL_PREFIX}{room_code}"


def presence_key(room_code: str) -> str:
    return f"room:{room_code}:presence"


class Hub:
    def __init__(self) -> None:
        # room code -> {connection_id: WebSocket} for sockets on *this* instance
        self._local: dict[str, dict[str, WebSocket]] = defaultdict(dict)
        self._pubsub = None
        self._reader: asyncio.Task | None = None

    # ------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        self._pubsub = redis().pubsub(ignore_subscribe_messages=True)
        await self._pubsub.psubscribe(f"{CHANNEL_PREFIX}*")
        self._reader = asyncio.create_task(self._read_loop(), name="hub-reader")
        log.info("hub subscribed to %s* as instance %s", CHANNEL_PREFIX, settings.instance_id)

    async def stop(self) -> None:
        if self._reader:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader
        if self._pubsub:
            await self._pubsub.punsubscribe(f"{CHANNEL_PREFIX}*")
            await self._pubsub.aclose()

    async def _read_loop(self) -> None:
        assert self._pubsub is not None
        async for message in self._pubsub.listen():
            if message.get("type") not in ("message", "pmessage"):
                continue
            try:
                room_code = message["channel"].removeprefix(CHANNEL_PREFIX)
                payload = json.loads(message["data"])
                await self._deliver_local(room_code, payload)
            except Exception:
                log.exception("failed to deliver pub/sub message")

    # ------------------------------------------------------------- registry
    async def register(self, room_code: str, conn_id: str, ws: WebSocket) -> None:
        self._local[room_code][conn_id] = ws

    async def unregister(self, room_code: str, conn_id: str) -> None:
        self._local.get(room_code, {}).pop(conn_id, None)
        if not self._local.get(room_code):
            self._local.pop(room_code, None)

    def local_count(self, room_code: str) -> int:
        return len(self._local.get(room_code, {}))

    # ---------------------------------------------------------- publishing
    async def publish(self, room_code: str, event: dict, skip_conn: str | None = None) -> None:
        """Broadcast an event to every instance serving this room.

        `skip_conn` travels inside the message rather than being applied locally,
        so the exclusion works no matter which instance holds that connection.
        """
        event["_skip"] = skip_conn
        event["_instance"] = settings.instance_id
        await redis().publish(channel(room_code), json.dumps(event, default=str))

    async def _deliver_local(self, room_code: str, payload: dict) -> None:
        skip = payload.pop("_skip", None)
        targets = list(self._local.get(room_code, {}).items())
        if not targets:
            return
        dead: list[str] = []
        for conn_id, ws in targets:
            if conn_id == skip:
                continue
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(conn_id)
        for conn_id in dead:
            await self.unregister(room_code, conn_id)

    # ------------------------------------------------------------- presence
    async def set_presence(self, room_code: str, user_id: str, data: dict) -> None:
        key = presence_key(room_code)
        await redis().hset(key, user_id, json.dumps(data, default=str))
        await redis().expire(key, PRESENCE_TTL * 4)

    async def clear_presence(self, room_code: str, user_id: str) -> None:
        await redis().hdel(presence_key(room_code), user_id)

    async def get_presence(self, room_code: str) -> list[dict]:
        raw = await redis().hgetall(presence_key(room_code))
        return [json.loads(v) for v in raw.values()]


hub = Hub()
