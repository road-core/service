"""Simple user quota limiter where each user have fixed quota."""

import logging
from datetime import datetime

import psycopg2

from ols.app.models.config import PostgresConfig
from ols.src.quota.quota_exceed_error import QuotaExceedError
from ols.src.quota.quota_limiter import QuotaLimiter

logger = logging.getLogger(__name__)


class UserQuotaLimiter(QuotaLimiter):
    """Simple user quota limiter where each user have fixed quota."""

    CREATE_QUOTA_TABLE = """
        CREATE TABLE IF NOT EXISTS user_quota_limiter (
            user_id         text NOT NULL,
            quota_limit     int NOT NULL,
            available       int,
            updated_at      timestamp with time zone,
            revoked_at      timestamp with time zone,
            PRIMARY KEY(user_id)
        );
        """

    INIT_QUOTA_FOR_USER = """
        INSERT INTO user_quota_limiter (user_id, quota_limit, available, revoked_at)
        VALUES (%s, %s, %s, %s)
        """

    SELECT_QUOTA_FOR_USER = """
        SELECT available
          FROM user_quota_limiter
         WHERE user_id=%s LIMIT 1
        """

    SET_AVAILABLE_QUOTA_FOR_USER = """
        UPDATE user_quota_limiter
           SET available=%s, updated_at=%s
         WHERE user_id=%s
        """

    UPDATE_AVAILABLE_QUOTA_FOR_USER = """
        UPDATE user_quota_limiter
           SET available=available+%s, updated_at=%s
         WHERE user_id=%s
        """

    def __init__(
        self, config: PostgresConfig, initial_quota: int = 0, increase_by: int = 0
    ) -> None:
        """Initialize quota limiter storage."""
        self.initial_quota = initial_quota
        self.increase_by = increase_by

        # initialize connection to DB
        self.connection = psycopg2.connect(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password,
            dbname=config.dbname,
            sslmode=config.ssl_mode,
            sslrootcert=config.ca_cert_path,
            gssencmode=config.gss_encmode,
        )
        self.connection.autocommit = True
        try:
            self._initialize_tables()
        except Exception as e:
            self.connection.close()
            logger.exception("Error initializing Postgres database:\n%s", e)
            raise

    def available_quota(self, user_id: str = "") -> int:
        """Retrieve available quota for given user."""
        with self.connection.cursor() as cursor:
            cursor.execute(
                UserQuotaLimiter.SELECT_QUOTA_FOR_USER,
                (user_id,),
            )
            value = cursor.fetchone()
            if value is None:
                self._init_quota(user_id)
                return self.initial_quota
            return value[0]

    def revoke_quota(self, user_id: str = "") -> None:
        """Revoke quota for given user."""
        # timestamp to be used
        updated_at = datetime.now()

        with self.connection.cursor() as cursor:
            cursor.execute(
                UserQuotaLimiter.SET_AVAILABLE_QUOTA_FOR_USER,
                (self.initial_quota, updated_at, user_id),
            )
            self.connection.commit()

    def increase_quota(self, user_id: str = "") -> None:
        """Increase quota for given user."""
        # timestamp to be used
        updated_at = datetime.now()

        with self.connection.cursor() as cursor:
            cursor.execute(
                UserQuotaLimiter.UPDATE_AVAILABLE_QUOTA_FOR_USER,
                (self.increase_by, updated_at, user_id),
            )
            self.connection.commit()

    def consume_tokens(
        self, input_tokens: int = 0, output_tokens: int = 0, user_id: str = ""
    ) -> None:
        """Consume tokens by given user."""
        to_be_consumed = input_tokens + output_tokens
        available = self.available_quota(user_id)

        # check if user still have available tokens to be consumed
        if available < to_be_consumed:
            e = QuotaExceedError(user_id, available, to_be_consumed)
            logger.exception("Quota exceed: %s", e)
            raise e

        # timestamp to be used
        updated_at = datetime.now()

        with self.connection.cursor() as cursor:
            cursor.execute(
                UserQuotaLimiter.UPDATE_AVAILABLE_QUOTA_FOR_USER,
                (-to_be_consumed, updated_at, user_id),
            )
            self.connection.commit()

    def _initialize_tables(self) -> None:
        """Initialize tables used by quota limiter."""
        cursor = self.connection.cursor()
        cursor.execute(UserQuotaLimiter.CREATE_QUOTA_TABLE)
        cursor.close()
        self.connection.commit()

    def _init_quota(self, user_id: str) -> None:
        """Initialize quota for given user."""
        # timestamp to be used
        revoked_at = datetime.now()

        with self.connection.cursor() as cursor:
            cursor.execute(
                UserQuotaLimiter.INIT_QUOTA_FOR_USER,
                (user_id, self.initial_quota, self.initial_quota, revoked_at),
            )
            self.connection.commit()
