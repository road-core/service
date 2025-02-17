"""Simple user quota limiter where each user have fixed quota."""

import logging

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
            PRIMARY KEY(user_id)
        );
        """

    INIT_QUOTA_FOR_USER = """
        INSERT INTO user_quota_limiter (user_id, quota_limit, available)
        VALUES (%s, %s, %s)
        """

    SELECT_QUOTA_FOR_USER = """
        SELECT available
          FROM user_quota_limiter
         WHERE user_id=%s LIMIT 1
        """

    UPDATE_AVAILABLE_QUOTA_FOR_USER = """
        UPDATE user_quota_limiter
           SET available=%s
         WHERE user_id=%s
        """

    def __init__(self, config: PostgresConfig, initial_quota: int) -> None:
        """Initialize quota limiter storage."""
        self.initial_quota = initial_quota

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

    def available_quota(self, user_id: str) -> int:
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

    def consume_tokens(
        self, user_id: str, input_tokens: int, output_tokens: int
    ) -> None:
        """Consume tokens by given user."""
        to_be_consumed = input_tokens + output_tokens
        available = self.available_quota(user_id)

        # check if user still have available tokens to be consumed
        if available < to_be_consumed:
            e = QuotaExceedError(user_id, available, to_be_consumed)
            logger.exception("Quota exceed: %s", e)
            raise e

        # update available tokens for user
        available -= to_be_consumed
        with self.connection.cursor() as cursor:
            cursor.execute(
                UserQuotaLimiter.UPDATE_AVAILABLE_QUOTA_FOR_USER, (available, user_id)
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
        with self.connection.cursor() as cursor:
            cursor.execute(
                UserQuotaLimiter.INIT_QUOTA_FOR_USER,
                (user_id, self.initial_quota, self.initial_quota),
            )
            self.connection.commit()
