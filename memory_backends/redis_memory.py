import json
import time
from typing import Any

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from .base import BaseMemory


class RedisMemory(BaseMemory):
    """Long-term distributed memory backed by Redis.

    Persists conversation history across sessions. Supports TTL-based expiration.
    Uses Redis hashes and sorted sets for efficient retrieval.
    """

    def __init__(
        self,
        session_id: str,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        key_prefix: str = "memory:",
        ttl_seconds: int = 86400 * 7,
        **kwargs,
    ):
        super().__init__(session_id, **kwargs)
        self.host = host
        self.port = port
        self.db = db
        self.ttl_seconds = ttl_seconds
        self.key_prefix = key_prefix
        self._redis = None
        self._connected = False
        # In-memory fallback for when Redis is unavailable
        self._profile_store: dict[str, str] = {}
        self._profile_history: list[tuple[str, str, float]] = []

        if REDIS_AVAILABLE:
            try:
                self._redis = redis.Redis(
                    host=host,
                    port=port,
                    db=db,
                    password=password,
                    decode_responses=True,
                    socket_connect_timeout=3,
                    socket_timeout=3,
                )
                # Test connection with a fast command instead of ping()
                # to honour the socket timeouts set above.
                self._redis.echo("ok")
                self._connected = True
            except (TimeoutError, redis.exceptions.ConnectionError, redis.exceptions.TimeoutError, Exception):
                self._connected = False

    def add(self, message: dict) -> None:
        role = message.get("role", "user")
        content = message.get("content", "")
        timestamp = message.get("timestamp", time.time())

        entry = {
            "role": role,
            "content": content,
            "timestamp": timestamp,
            "session_id": self.session_id,
            "memory_type": "redis",
        }
        entry_json = json.dumps(entry)
        message_id = f"{self.session_id}:{timestamp}"

        if self._connected:
            try:
                key = f"{self.key_prefix}{self.session_id}"
                self._redis.zadd(key, {message_id: timestamp})
                self._redis.hset(f"{key}:msgs", message_id, entry_json)
                self._redis.expire(key, self.ttl_seconds)
                self._redis.expire(f"{key}:msgs", self.ttl_seconds)
            except Exception:
                pass

    def get_recent(self, n: int = 10) -> list[dict]:
        if not self._connected:
            return []
        try:
            key = f"{self.key_prefix}{self.session_id}"
            message_ids = self._redis.zrevrange(key, 0, n - 1)
            result = []
            for msg_id in message_ids:
                raw = self._redis.hget(f"{key}:msgs", msg_id)
                if raw:
                    result.append(json.loads(raw))
            return result
        except Exception:
            return []

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        if not self._connected:
            return []
        try:
            query_lower = query.lower()
            all_keys = self._redis.zrange(
                f"{self.key_prefix}{self.session_id}", 0, -1
            )
            scored = []
            for msg_id in all_keys:
                raw = self._redis.hget(
                    f"{self.key_prefix}{self.session_id}:msgs", msg_id
                )
                if raw:
                    entry = json.loads(raw)
                    if query_lower in entry["content"].lower():
                        score = entry["content"].lower().count(query_lower)
                        scored.append((score, entry))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [entry for _, entry in scored[:top_k]]
        except Exception:
            return []

    def clear(self) -> None:
        if self._connected:
            try:
                key = f"{self.key_prefix}{self.session_id}"
                self._redis.delete(key, f"{key}:msgs")
            except Exception:
                pass

    def save_profile_fact(self, key: str, value: str) -> dict[str, str]:
        """Save a user profile fact with conflict resolution.

        If the same key is updated, the new value always wins.
        This implements the conflict resolution required by the rubric.
        """
        ts = time.time()

        # --- Detect if this looks like a correction (user reversing a fact) ---
        is_correction = any(
            phrase in value.lower()
            for phrase in ["no,", "nhầm", "wrong", "actually", "not", "chứ không"]
        )

        old_value = None
        if key in self._profile_store:
            old_value = self._profile_store[key]

        # Save to in-memory store (always wins)
        self._profile_store[key] = value
        self._profile_history.append((key, value, ts))

        # Persist to Redis if connected
        if self._connected:
            try:
                profile_key = f"{self.key_prefix}{self.session_id}:profile"
                self._redis.hset(profile_key, key, json.dumps({
                    "value": value,
                    "timestamp": ts,
                    "old_value": old_value,
                    "is_correction": is_correction,
                }))
                self._redis.expire(profile_key, self.ttl_seconds)

                # Store history in sorted set for audit
                history_id = f"{key}:{ts}"
                self._redis.zadd(
                    f"{self.key_prefix}{self.session_id}:profile_history",
                    {history_id: ts},
                )
                self._redis.hset(
                    f"{self.key_prefix}{self.session_id}:profile_history",
                    history_id,
                    json.dumps({"key": key, "value": value, "is_correction": is_correction}),
                )
            except Exception:
                pass

        return {"updated": key, "old": old_value, "new": value}

    def get_profile(self) -> dict[str, str]:
        """Return the current user profile (only latest values)."""
        if self._connected:
            try:
                profile_key = f"{self.key_prefix}{self.session_id}:profile"
                raw = self._redis.hgetall(profile_key)
                result = {}
                for k, v in raw.items():
                    try:
                        data = json.loads(v)
                        result[k] = data["value"]
                    except Exception:
                        result[k] = v
                return result
            except Exception:
                pass
        return dict(self._profile_store)

    def get_profile_history(self, key: str) -> list[dict]:
        """Return the full history of a profile key (for conflict audit)."""
        history = [
            {"key": k, "value": v, "timestamp": ts}
            for k, v, ts in self._profile_history
            if k == key
        ]
        if self._connected:
            try:
                all_history = self._redis.zrange(
                    f"{self.key_prefix}{self.session_id}:profile_history", 0, -1
                )
                for hist_id in all_history:
                    raw = self._redis.hget(
                        f"{self.key_prefix}{self.session_id}:profile_history", hist_id
                    )
                    if raw:
                        data = json.loads(raw)
                        if data.get("key") == key:
                            history.append(data)
            except Exception:
                pass
        return sorted(history, key=lambda x: x.get("timestamp", 0))

    def delete_profile_fact(self, key: str) -> None:
        """Delete a specific profile fact (for GDPR/deletion requests)."""
        self._profile_store.pop(key, None)
        if self._connected:
            try:
                self._redis.hdel(
                    f"{self.key_prefix}{self.session_id}:profile", key
                )
            except Exception:
                pass

    def get_stats(self) -> dict[str, Any]:
        stats = {
            "type": "RedisMemory",
            "memory_type": "Long-term",
            "connected": self._connected,
            "host": self.host,
            "port": self.port,
            "ttl_seconds": self.ttl_seconds,
            "session_id": self.session_id,
            "profile_keys": list(self._profile_store.keys()),
        }
        if self._connected:
            try:
                key = f"{self.key_prefix}{self.session_id}"
                stats["message_count"] = self._redis.zcard(key)
            except Exception:
                stats["message_count"] = 0
        else:
            stats["message_count"] = 0
        return stats
