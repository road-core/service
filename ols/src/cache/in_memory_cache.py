"""In-memory LRU cache implemenetation."""

from __future__ import annotations

import threading
from collections import deque
from typing import TYPE_CHECKING, Any

from ols.app.models.models import CacheEntry

if TYPE_CHECKING:
    from ols.app.models.config import InMemoryCacheConfig
# pylint: disable-next=C0413
from ols.src.cache.cache import Cache


class InMemoryCache(Cache):
    """An in-memory LRU cache implementation in O(1) time."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls: type[InMemoryCache], config: InMemoryCacheConfig) -> InMemoryCache:
        """Implement Singleton pattern with thread safety."""
        with cls._lock:
            if not cls._instance:
                cls._instance = super().__new__(cls)
                cls._instance.initialize_cache(config)
        return cls._instance

    def initialize_cache(self, config: InMemoryCacheConfig) -> None:
        """Initialize the InMemoryCache."""
        # pylint: disable=W0201
        self.capacity = config.max_entries
        self.deque: deque[str] = deque()
        self.cache: dict[str, list[dict[str, Any]]] = {}

    def get(
        self, user_id: str, conversation_id: str, skip_user_id_check: bool = False
    ) -> list[CacheEntry]:
        """Get the value associated with the given key.

        Args:
          user_id: User identification.
          conversation_id: Conversation ID unique for given user.
          skip_user_id_check: Skip user_id suid check.

        Returns:
          The value associated with the key, or `None` if the key is not present.
        """
        key = super().construct_key(user_id, conversation_id, skip_user_id_check)

        if key not in self.cache:
            return None

        self.deque.remove(key)
        self.deque.appendleft(key)
        value = self.cache[key].copy()
        return [CacheEntry.from_dict(cache_entry) for cache_entry in value]

    def insert_or_append(
        self,
        user_id: str,
        conversation_id: str,
        cache_entry: CacheEntry,
        skip_user_id_check: bool = False,
    ) -> None:
        """Set the value if a key is not present or else simply appends.

        Args:
            user_id: User identification.
            conversation_id: Conversation ID unique for given user.
            cache_entry: The `CacheEntry` object to store.
            skip_user_id_check: Skip user_id suid check.
        """
        key = super().construct_key(user_id, conversation_id, skip_user_id_check)
        value = cache_entry.to_dict()

        with self._lock:
            if key not in self.cache:
                if len(self.deque) == self.capacity:
                    oldest = self.deque.pop()
                    del self.cache[oldest]
                self.cache[key] = [value]
            else:
                self.deque.remove(key)
                old_value = self.cache[key]
                old_value.append(value)
                self.cache[key] = old_value
            self.deque.appendleft(key)

    def delete(self, user_id: str, conversation_id: str, skip_user_id_check: bool = False) -> bool:
        """Delete all entries for a given conversation.

        Args:
            user_id: User identification.
            conversation_id: Conversation ID unique for given user.
            skip_user_id_check: Skip user_id suid check.

        Returns:
            bool: True if entries were deleted, False if key wasn't found.
        """
        key = super().construct_key(user_id, conversation_id, skip_user_id_check)

        with self._lock:
            if key not in self.cache:
                return False

            # Remove from both cache and deque
            del self.cache[key]
            self.deque.remove(key)
            return True

    def list(self, user_id: str, skip_user_id_check: bool = False) -> list[str]:
        """List all conversations for a given user_id.

        Args:
            user_id: User identification.
            skip_user_id_check: Skip user_id suid check.

        Returns:
            A list of conversation ids from the cache
        """
        conversation_ids = []
        super()._check_user_id(user_id, skip_user_id_check)
        prefix = f"{user_id}{Cache.COMPOUND_KEY_SEPARATOR}"

        with self._lock:
            for key in self.cache:
                if key.startswith(prefix):
                    # Extract conversation_id from the key
                    conversation_id = key[len(prefix) :]
                    conversation_ids.append(conversation_id)

        return conversation_ids
