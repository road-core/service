"""Any exception that can occur when user does not have enough tokens available."""


class QuotaExceedError(Exception):
    """Any exception that can occur when user does not have enough tokens available."""

    def __init__(self, subject_id: str, subject_type: str, available: int, needed: int):
        """Construct exception object."""
        match subject_type:
            case "u":
                message = f"User {subject_id} has {available} tokens, but {needed} tokens are needed"  # noqa: E501
            case "c":
                message = (
                    f"Cluster has {available} tokens, but {needed} tokens are needed"
                )
            case _:
                message = f"Unknown subject {subject_id} has {available} tokens, but {needed} tokens are needed"  # noqa: E501

        # call the base class constructor with the parameters it needs
        super().__init__(message)

        # custom attributes
        self.subject_id = subject_id
        self.available = available
        self.needed = needed
