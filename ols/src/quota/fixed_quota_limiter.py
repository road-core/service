"""Simple quota limiter where each user have fixed quota."""

from ols.src.quota import QuotaLimiter


class FixedQuotaLimiter(QuotaLimiter):
    """Simple quota limiter where each user have fixed quota."""

    CREATE_QUOTA_TABLE = """
        CREATE TABLE IF NOT EXISTS fixed_quota_limiter (
            user_id         text NOT NULL,
            quota_limit     int NOT NULL,
            actual_usage    int,
            PRIMARY KEY(user_id)
        );
        """


    def __init__(self, config: PostgresConfig, initial_quota: int) -> None:
        """Initialize quota limiter storage."""
        self.capacity = config.max_entries

        # initialize connection to DB
        self.conn = psycopg2.connect(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password,
            dbname=config.dbname,
            sslmode=config.ssl_mode,
            sslrootcert=config.ca_cert_path,
        )
        self.conn.autocommit = True
        try:
            self._initialize_tables()
        except Exception as e:
            self.conn.close()
            logger.exception("Error initializing Postgres database:\n%s", e)
            raise

    def available_quota(self, user_id: str) -> int:
        """Retrieve available quota for given user."""

    def consume_tokens(self, user_id: str, input_tokens: int, output_tokens: int) -> None:
        """Consume tokens by given user."""

    def _initialize_tables(conn) -> None:
        """Initialize tables used by quota limiter."""
        cur = conn.cursor()
        cur.execute(FixedQuotaLimiter.CREATE_QUOTA_TABLE)
        cur.close()
        conn.commit()
