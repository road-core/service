"""Abstract class that is parent for all quota limiter implementations."""

from abc import ABC, abstractmethod


class QuotaLimiter(ABC):
    """Abstract class that is parent for all quota limiter implementations."""

    @abstractmethod
    def available_quota(self, user_id: str) -> int:
        """Retrieve available quota for given user."""

    @abstractmethod
    def consume_tokens(self, user_id: str, input_tokens: int, output_tokens: int) -> None:
        """Consume tokens by given user."""
