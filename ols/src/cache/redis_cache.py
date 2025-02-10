"""Cache that uses Redis to store cached values."""

import json
import threading
from typing import Any, Dict, Optional

import redis
from redis.backoff import ExponentialBackoff
from redis.exceptions import BusyLoadingError, RedisError
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.retry import Retry

from ols.app.models.config import RedisConfig
from ols.app.models.models import CacheEntry, MessageDecoder, MessageEncoder
from ols.src.cache.cache import Cache


class RedisCache(Cache):
    """Cache that uses Redis to store cached values."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls: type["RedisCache"], config: RedisConfig) -> "RedisCache":
        """Create a new instance of the `RedisCache` class."""
        with cls._lock:
            if not cls._instance:
                cls._instance = super().__new__(cls)
                cls._instance.initialize_redis(config)
        return cls._instance

    def initialize_redis(self, config: RedisConfig) -> None:
        """Initialize the Redis client and logger.

        This method sets up the Redis client with custom configuration parameters.
        """
        kwargs: dict[str, Any] = {}
        if config.password is not None:
            kwargs["password"] = config.password
        if config.ca_cert_path is not None:
            kwargs["ssl"] = True
            kwargs["ssl_cert_reqs"] = "required"
            kwargs["ssl_ca_certs"] = config.ca_cert_path

        # setup Redis retry logic
        retry: Optional[Retry] = None
        if config.number_of_retries is not None and config.number_of_retries > 0:
            retry = Retry(ExponentialBackoff(), config.number_of_retries)  # type: ignore [no-untyped-call]

        retry_on_error: Optional[list[type[RedisError]]] = None
        if config.retry_on_error:
            retry_on_error = [BusyLoadingError, RedisConnectionError]

        # initialize Redis client
        # pylint: disable=W0201
        self.redis_client = redis.StrictRedis(
            host=str(config.host),
            port=int(config.port),
            decode_responses=False,  # we store serialized messages as bytes, not strings
            retry=retry,
            retry_on_timeout=bool(config.retry_on_timeout),
            retry_on_error=retry_on_error,
            **kwargs,
        )
        # Set custom configuration parameters
        self.redis_client.config_set("maxmemory", config.max_memory)
        self.redis_client.config_set("maxmemory-policy", config.max_memory_policy)

    def get(
        self, user_id: str, conversation_id: str, skip_user_id_check: bool = False
    ) -> list[CacheEntry]:
        """Get the value associated with the given key.

        Args:
            user_id: User identification.
            conversation_id: Conversation ID unique for given user.
            skip_user_id_check: Skip user_id suid check.

        Returns:
             A list of CacheEntry objects, or None if not found.
        """
        key = super().construct_key(user_id, conversation_id, skip_user_id_check)

        value = self.redis_client.get(key)
        if value is None:
            return None

        decoded_value = json.loads(value, cls=MessageDecoder)
        cache_entries = decoded_value["history"]  # New format
        return cache_entries

    def get_db_entry(
        self, user_id: str, conversation_id: str, skip_user_id_check: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Get the db entry associated with the given key.

        Args:
            user_id: User identification.
            conversation_id: Conversation ID unique for given user.
            skip_user_id_check: Skip user_id suid check.

        Returns:
            A dictionary containing history and topic_summary, or None if not found.
        """
        key = super().construct_key(user_id, conversation_id, skip_user_id_check)

        value = self.redis_client.get(key)
        if value is None:
            return None

        return json.loads(value, cls=MessageDecoder)

    def insert_or_append(
        self,
        user_id: str,
        conversation_id: str,
        cache_entry: CacheEntry,
        topic_summary: str = "",
        skip_user_id_check: bool = False,
    ) -> None:
        """Set the value associated with the given key.

        Args:
            user_id: User identification.
            conversation_id: Conversation ID unique for given user.
            cache_entry: The `CacheEntry` object to store.
            topic_summary: Summary of the conversation's initial topic.
            skip_user_id_check: Skip user_id suid check.

        Raises:
            OutOfMemoryError: If item is evicted when Redis allocated
                memory is higher than maxmemory.
        """
        key = super().construct_key(user_id, conversation_id, skip_user_id_check)

        with self._lock:
            old_value = self.get_db_entry(user_id, conversation_id, skip_user_id_check)
            if old_value:
                old_value["history"].append(cache_entry)
            else:
                old_value = {"history": [cache_entry], "topic_summary": topic_summary}
            self.redis_client.set(key, json.dumps(old_value, cls=MessageEncoder))

    def delete(
        self, user_id: str, conversation_id: str, skip_user_id_check: bool = False
    ) -> bool:
        """Delete conversation history for a given user_id and conversation_id.

        Args:
            user_id: User identification.
            conversation_id: Conversation ID unique for given user.
            skip_user_id_check: Skip user_id suid check.

        Returns:
            bool: True if the conversation was deleted, False if not found.
        """
        key = super().construct_key(user_id, conversation_id, skip_user_id_check)
        # Redis del() returns the number of keys that were removed
        return bool(self.redis_client.delete(key))

    def list(
        self, user_id: str, skip_user_id_check: bool = False
    ) -> list[dict[str, str]]:
        """List all conversations for a given user_id.

        Args:
            user_id: User identification.
            skip_user_id_check: Skip user_id suid check.

        Returns:
             A list of dictionaries containing conversation_id and topic_summary
        """
        # Get all keys matching the user_id prefix
        super()._check_user_id(user_id, skip_user_id_check)
        prefix = f"{user_id}{Cache.COMPOUND_KEY_SEPARATOR}"
        pattern = f"{prefix}*"
        keys = self.redis_client.keys(pattern)

        # Initialize result list
        conversations = []

        # Fetch data for each conversation
        for key in keys:
            # Extract conversation_id from the key
            conversation_id = key[len(prefix) :]

            # Get the conversation data
            conversation_data = self.get_db_entry(
                user_id, conversation_id, skip_user_id_check
            )
            if conversation_data is not None:
                conversations.append(
                    {
                        "conversation_id": conversation_id,
                        "topic_summary": conversation_data.get("topic_summary", ""),
                    }
                )

        return conversations
