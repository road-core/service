"""Abstract class that is parent for all quota limiter implementations."""

from abc import ABC, abstractmethod


class QuotaLimiter(ABC):
    """Abstract class that is parent for all quota limiter implementations."""

    @abstractmethod
    def available_quota(self) -> int:
        """Retrieve available quota for given user."""

    @abstractmethod
    def revoke_quota(self) -> None:
        """Revoke quota for given user."""

    @abstractmethod
    def increase_quota(self) -> None:
        """Increase quota for given user."""

    @abstractmethod
    def consume_tokens(self, input_tokens: int, output_tokens: int) -> None:
        """Consume tokens by given user."""
