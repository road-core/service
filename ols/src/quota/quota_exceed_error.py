"""Any exception that can occur when user does not have enough tokens available."""


class QuotaExceedError(Exception):
    """Any exception that can occur when user does not have enough tokens available."""

    def __init__(self, user_id: str, available: int, needed: int):
        """Construct exception object."""
        message = (
            f"User {user_id} has {available} tokens, but {needed} tokens are needed"
        )
        # call the base class constructor with the parameters it needs
        super().__init__(message)

        # custom attributes
        self.user_id = user_id
        self.available = available
        self.needed = needed
