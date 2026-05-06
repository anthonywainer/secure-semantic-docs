from collections.abc import Callable
from datetime import datetime
from functools import wraps
from typing import Any

from secure_semantic_docs.core.logging import get_logger
from secure_semantic_docs.core.settings import BaseSettings

logger = get_logger(BaseSettings.APP_NAME)


def ingest_log_execution(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to log execution time and status of a function."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = datetime.now()

        try:
            result = func(*args, **kwargs)
            logger.info("Ingest finished successfully")
            return result

        except Exception:
            logger.exception("Ingest failed")
            raise

        finally:
            duration = datetime.now() - start_time
            logger.info(f"Ingest completed in {duration}")

    return wrapper
