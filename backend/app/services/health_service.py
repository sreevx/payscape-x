"""Health check service.

The service reports liveness honestly: the API is "ok" if it is serving
requests, while database connectivity is reported separately. A down
database degrades the report — it never fakes success.

The database probe is hard-bounded (DB_PROBE_TIMEOUT_SECONDS) so a slow or
unreachable database can never hang the health endpoint.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.config import get_settings
from app.schemas.health import HealthResponse

logger = logging.getLogger(__name__)

DB_PROBE_TIMEOUT_SECONDS = 2.0


def _probe_database(engine: Engine) -> bool:
    """Return True when the database answers SELECT 1."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        # Fail fast and log it — but never surface the traceback.
        logger.warning("Database health check failed", exc_info=True)
        return False


def build_health_response(engine: Engine) -> HealthResponse:
    """Build a health response, probing the database without faking results."""
    database_status: str = "unavailable"

    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(_probe_database, engine)
    try:
        if future.result(timeout=DB_PROBE_TIMEOUT_SECONDS):
            database_status = "ok"
    except TimeoutError:
        logger.warning(
            "Database health check timed out after %ss",
            DB_PROBE_TIMEOUT_SECONDS,
        )
    finally:
        # Do not wait for the abandoned probe thread — the response is due.
        pool.shutdown(wait=False)

    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        version=settings.app_version,
        database=database_status,  # type: ignore[arg-type]
    )