"""Retry utilities for network operations."""

from __future__ import annotations

import json
import logging
import os
from functools import wraps
from typing import Any, Callable

from tenacity import (
    Retrying,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
)

logger = logging.getLogger(__name__)

# Default retry configuration
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_MIN_WAIT = 2
DEFAULT_MAX_WAIT = 10

# Exceptions that should trigger a retry
RETRYABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,
)


def _safe_getattr(obj: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(obj, name)
    except (AttributeError, KeyError):
        return default


def get_retry_config() -> dict[str, Any]:
    """Get retry configuration from environment variables."""
    return {
        "max_attempts": int(os.getenv("RETRY_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS)),
        "min_wait": int(os.getenv("RETRY_MIN_WAIT", DEFAULT_MIN_WAIT)),
        "max_wait": int(os.getenv("RETRY_MAX_WAIT", DEFAULT_MAX_WAIT)),
    }


def _get_status_code(exception: Exception) -> int | None:
    """Extract an HTTP status code from requests or urllib style exceptions."""
    status_code = _safe_getattr(exception, "code")
    if isinstance(status_code, int):
        return status_code

    response = _safe_getattr(exception, "response")
    if response is not None:
        status_code = _safe_getattr(response, "status_code")
        if isinstance(status_code, int):
            return status_code

    return None


def _headers_get(headers: Any, name: str) -> str | None:
    if headers is None:
        return None
    getter = getattr(headers, "get", None)
    if callable(getter):
        value = getter(name)
        if value is None:
            value = getter(name.lower())
        return str(value).strip() if value is not None else None
    return None


def _parse_wait_seconds(value: Any) -> float | None:
    try:
        wait_seconds = float(value)
    except (TypeError, ValueError):
        return None
    if wait_seconds < 0:
        return None
    return wait_seconds


def _retry_after_from_headers(exception: Exception) -> float | None:
    retry_after = _headers_get(_safe_getattr(exception, "headers"), "Retry-After")
    if retry_after is None:
        response = _safe_getattr(exception, "response")
        response_headers = _safe_getattr(response, "headers") if response is not None else None
        retry_after = _headers_get(response_headers, "Retry-After")
    return _parse_wait_seconds(retry_after)


def _retry_after_from_detail(exception: Exception) -> float | None:
    detail = _safe_getattr(exception, "retry_detail", "")
    if not detail:
        return None
    try:
        payload = json.loads(detail)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return _parse_wait_seconds(payload.get("reset"))


def get_retry_after_seconds(exception: Exception) -> float | None:
    """Return server-requested wait seconds for HTTP 429 responses, if present."""
    if _get_status_code(exception) != 429:
        return None
    retry_after = _retry_after_from_headers(exception)
    if retry_after is not None:
        return retry_after
    return _retry_after_from_detail(exception)


def should_retry(exception: Exception) -> bool:
    """Determine if an exception should trigger a retry.
    
    Args:
        exception: The exception that was raised
        
    Returns:
        True if the operation should be retried, False otherwise
    """
    status_code = _get_status_code(exception)
    if status_code is not None:
        return status_code in (429, 500, 502, 503, 504)

    if isinstance(exception, RETRYABLE_EXCEPTIONS):
        return True

    return False


def with_retry(
    func: Callable[..., Any] | None = None,
    *,
    max_attempts: int | None = None,
    min_wait: int | None = None,
    max_wait: int | None = None,
) -> Any:
    """Decorator to add retry logic to a function.
    
    Can be used as:
        @with_retry
        def my_func(): ...
        
        @with_retry(max_attempts=5)
        def my_func(): ...
    
    Args:
        func: The function to wrap
        max_attempts: Maximum number of retry attempts (default from env)
        min_wait: Minimum wait time between retries in seconds (default from env)
        max_wait: Maximum wait time between retries in seconds (default from env)
        
    Returns:
        Wrapped function with retry logic
    """
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            config = get_retry_config()
            attempts = max_attempts or config["max_attempts"]
            min_w = min_wait or config["min_wait"]
            max_w = max_wait or config["max_wait"]
            fallback_wait = wait_exponential(multiplier=1, min=min_w, max=max_w)

            def wait_for_retry(retry_state: Any) -> float:
                exception = retry_state.outcome.exception() if retry_state.outcome else None
                if exception is not None:
                    retry_after = get_retry_after_seconds(exception)
                    if retry_after is not None:
                        return retry_after
                return fallback_wait(retry_state)
            
            retryer = Retrying(
                stop=stop_after_attempt(attempts),
                wait=wait_for_retry,
                retry=retry_if_exception(should_retry),
                reraise=True,
                before_sleep=lambda retry_state: logger.warning(
                    f"{fn.__name__} failed (attempt {retry_state.attempt_number}/{attempts}), retrying..."
                ),
            )
            
            try:
                result = retryer(fn, *args, **kwargs)
                if retryer.statistics.get("attempt_number", 1) > 1:
                    logger.info(f"{fn.__name__} succeeded after retry")
                return result
            except Exception as e:
                logger.error(f"{fn.__name__} failed after all retries: {e}")
                raise
        
        return wrapper
    
    if func is not None:
        return decorator(func)
    return decorator
