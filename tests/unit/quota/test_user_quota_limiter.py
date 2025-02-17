"""Unit tests for UserQuotaLimiter class."""

from unittest.mock import MagicMock, call, patch

import pytest

from ols.app.models.config import PostgresConfig
from ols.src.quota.user_quota_limiter import UserQuotaLimiter


@patch("psycopg2.connect")
def test_init_storage_failure_detection(mock_connect):
    """Test the exception handling for storage initialize operation."""
    exception_message = "Exception during PostgreSQL storage."
    mock_connect.return_value.cursor.return_value.execute.side_effect = Exception(
        exception_message
    )

    # try to connect to mocked Postgres
    config = PostgresConfig()
    with pytest.raises(Exception, match=exception_message):
        UserQuotaLimiter(config, 0)

    # connection must be closed in case of exception
    mock_connect.return_value.close.assert_called_once_with()


@patch("psycopg2.connect")
def test_init_quota(mock_connect):
    """Test the init quota operation."""
    quota_limit = 100
    user_id = "1234"

    # mock the query result - with empty storage
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None
    mock_connect.return_value.cursor.return_value.__enter__.return_value = mock_cursor

    # initialize Postgres storage
    config = PostgresConfig()
    q = UserQuotaLimiter(config, quota_limit)

    # init quota for given user
    q._init_quota(user_id)

    # new record should be inserted into storage
    mock_cursor.execute.assert_called_once_with(
        UserQuotaLimiter.INIT_QUOTA_FOR_USER, (user_id, quota_limit, quota_limit)
    )


@patch("psycopg2.connect")
def test_available_quota_with_data(mock_connect):
    """Test the get available quota operation."""
    quota_limit = 100
    available_quota = 50
    user_id = "1234"

    # mock the query result - available data in the table
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (available_quota,)
    mock_connect.return_value.cursor.return_value.__enter__.return_value = mock_cursor

    # initialize Postgres storage
    config = PostgresConfig()
    q = UserQuotaLimiter(config, quota_limit)

    # try to retrieve available quota for given user
    available = q.available_quota(user_id)

    # quota for given user should be read from storage
    mock_cursor.execute.assert_called_once_with(
        UserQuotaLimiter.SELECT_QUOTA_FOR_USER, (user_id,)
    )
    assert available == available_quota


@patch("psycopg2.connect")
def test_available_quota_no_data(mock_connect):
    """Test the get available quota operation."""
    quota_limit = 100
    user_id = "1234"

    # mock the query result - no data
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None
    mock_connect.return_value.cursor.return_value.__enter__.return_value = mock_cursor

    # initialize Postgres storage
    config = PostgresConfig()
    q = UserQuotaLimiter(config, quota_limit)

    # try to retrieve available quota for given user
    available = q.available_quota(user_id)

    # quota for given user should be read from storage
    # and the initialization of new record should be made
    calls = [
        call(UserQuotaLimiter.SELECT_QUOTA_FOR_USER, (user_id,)),
        call(
            UserQuotaLimiter.INIT_QUOTA_FOR_USER,
            (user_id, quota_limit, quota_limit),
        ),
    ]
    mock_cursor.execute.assert_has_calls(calls, any_order=True)
    assert available == quota_limit


@patch("psycopg2.connect")
def test_consume_tokens_not_enough(mock_connect):
    """Test the operation to consume tokens."""
    to_be_consumed = 100
    available_tokens = 50
    quota_limit = 100
    user_id = "1234"

    # mock the query result - no data
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (available_tokens,)
    mock_connect.return_value.cursor.return_value.__enter__.return_value = mock_cursor

    # initialize Postgres storage
    config = PostgresConfig()
    q = UserQuotaLimiter(config, quota_limit)

    # try to consume tokens
    with pytest.raises(
        Exception, match="User 1234 has 50 tokens, but 100 tokens are needed"
    ):
        q.consume_tokens(user_id, to_be_consumed, 0)

    # quota for given user should be read from storage
    mock_cursor.execute.assert_called_once_with(
        UserQuotaLimiter.SELECT_QUOTA_FOR_USER, (user_id,)
    )


@patch("psycopg2.connect")
def test_consume_tokens_enough_tokens(mock_connect):
    """Test the operation to consume tokens."""
    to_be_consumed = 50
    available_tokens = 100
    quota_limit = 100
    user_id = "1234"

    # mock the query result - no data
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (available_tokens,)
    mock_connect.return_value.cursor.return_value.__enter__.return_value = mock_cursor

    # initialize Postgres storage
    config = PostgresConfig()
    q = UserQuotaLimiter(config, quota_limit)

    # try to consume tokens
    q.consume_tokens(user_id, to_be_consumed, 0)

    calls = [
        # quota for given user should be read from storage
        call(UserQuotaLimiter.SELECT_QUOTA_FOR_USER, (user_id,)),
        # and the quota should be updated accordingly
        call(
            UserQuotaLimiter.UPDATE_AVAILABLE_QUOTA_FOR_USER,
            (available_tokens - to_be_consumed, user_id),
        ),
    ]
    mock_cursor.execute.assert_has_calls(calls, any_order=True)
