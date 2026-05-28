"""Unit tests for retry_utils module."""

from __future__ import annotations

import os
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import requests

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.retry_utils import (
    get_retry_config,
    get_retry_after_seconds,
    should_retry,
    with_retry,
    RETRYABLE_EXCEPTIONS,
)


class TestGetRetryConfig:
    """Tests for get_retry_config function."""
    
    def test_default_values(self):
        """Test default configuration values."""
        with patch.dict(os.environ, {}, clear=True):
            config = get_retry_config()
            assert config["max_attempts"] == 3
            assert config["min_wait"] == 2
            assert config["max_wait"] == 10
    
    def test_custom_values_from_env(self):
        """Test custom configuration from environment variables."""
        env = {
            "RETRY_MAX_ATTEMPTS": "5",
            "RETRY_MIN_WAIT": "1",
            "RETRY_MAX_WAIT": "30",
        }
        with patch.dict(os.environ, env, clear=True):
            config = get_retry_config()
            assert config["max_attempts"] == 5
            assert config["min_wait"] == 1
            assert config["max_wait"] == 30


class TestShouldRetry:
    """Tests for should_retry function."""
    
    def test_retry_on_connection_error(self):
        """Test retry on ConnectionError."""
        assert should_retry(ConnectionError("connection failed")) is True
    
    def test_retry_on_timeout_error(self):
        """Test retry on TimeoutError."""
        assert should_retry(TimeoutError("request timed out")) is True
    
    def test_retry_on_os_error(self):
        """Test retry on OSError."""
        assert should_retry(OSError("network unreachable")) is True
    
    def test_no_retry_on_value_error(self):
        """Test no retry on ValueError."""
        assert should_retry(ValueError("invalid value")) is False
    
    def test_no_retry_on_key_error(self):
        """Test no retry on KeyError."""
        assert should_retry(KeyError("missing key")) is False
    
    def test_retry_on_http_500(self):
        """Test retry on HTTP 500 error."""
        response = MagicMock(status_code=500)
        exception = requests.HTTPError(response=response)
        assert should_retry(exception) is True
    
    def test_retry_on_http_503(self):
        """Test retry on HTTP 503 error."""
        response = MagicMock(status_code=503)
        exception = requests.HTTPError(response=response)
        assert should_retry(exception) is True
    
    def test_retry_on_http_429(self):
        """Test retry on HTTP 429 (rate limit) error."""
        response = MagicMock(status_code=429)
        exception = requests.HTTPError(response=response)
        assert should_retry(exception) is True
    
    def test_no_retry_on_http_404(self):
        """Test no retry on HTTP 404 error."""
        response = MagicMock(status_code=404)
        exception = requests.HTTPError(response=response)
        assert should_retry(exception) is False


class TestGetRetryAfterSeconds:
    """Tests for server-provided retry wait times."""

    def test_reads_requests_retry_after_header(self):
        """Test parsing Retry-After from requests-style responses."""
        response = MagicMock(status_code=429, headers={"Retry-After": "33"})
        exception = requests.HTTPError(response=response)

        assert get_retry_after_seconds(exception) == 33

    def test_respects_zero_retry_after_header(self):
        """Test Retry-After zero is treated as an explicit server value."""
        response = MagicMock(status_code=429, headers={"Retry-After": "0"})
        exception = requests.HTTPError(response=response)
        exception.retry_detail = '{"reset":29}'

        assert get_retry_after_seconds(exception) == 0

    def test_reads_urllib_retry_after_header(self):
        """Test parsing Retry-After from urllib-style HTTP errors."""
        headers = {"Retry-After": "31"}
        exception = urllib.error.HTTPError("https://example.test", 429, "Too Many Requests", headers, None)

        assert get_retry_after_seconds(exception) == 31

    def test_reads_buildkite_reset_detail(self):
        """Test parsing Buildkite rate-limit reset seconds from captured body."""
        exception = urllib.error.HTTPError("https://example.test", 429, "Too Many Requests", {}, None)
        exception.retry_detail = '{"message":"rate limited","reset":29}'

        assert get_retry_after_seconds(exception) == 29

    def test_ignores_retry_detail_for_non_rate_limit(self):
        """Test reset detail only applies to HTTP 429."""
        exception = urllib.error.HTTPError("https://example.test", 500, "Internal Server Error", {}, None)
        exception.retry_detail = '{"reset":29}'

        assert get_retry_after_seconds(exception) is None


class TestWithRetry:
    """Tests for with_retry decorator."""
    
    def test_successful_function(self):
        """Test that successful function returns normally."""
        @with_retry
        def successful_func():
            return "success"
        
        result = successful_func()
        assert result == "success"
    
    def test_retry_on_retryable_error(self):
        """Test that retryable errors trigger retries."""
        call_count = [0]
        
        @with_retry(max_attempts=3, min_wait=0, max_wait=1)
        def failing_then_succeeding_func():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError("connection failed")
            return "success"
        
        result = failing_then_succeeding_func()
        assert result == "success"
        assert call_count[0] == 3
    
    def test_fail_after_max_attempts(self):
        """Test that function fails after max attempts."""
        call_count = [0]
        
        @with_retry(max_attempts=2, min_wait=0, max_wait=1)
        def always_failing_func():
            call_count[0] += 1
            raise ConnectionError("connection failed")
        
        with pytest.raises(ConnectionError):
            always_failing_func()
        
        assert call_count[0] == 2
    
    def test_no_retry_on_non_retryable_error(self):
        """Test that non-retryable errors don't trigger retries."""
        call_count = [0]
        
        @with_retry(max_attempts=3, min_wait=0, max_wait=1)
        def non_retryable_error_func():
            call_count[0] += 1
            raise ValueError("invalid value")
        
        with pytest.raises(ValueError):
            non_retryable_error_func()
        
        # Should only be called once (no retries)
        assert call_count[0] == 1
    
    def test_decorator_with_args(self):
        """Test decorator with explicit arguments."""
        @with_retry(max_attempts=5, min_wait=1, max_wait=5)
        def func():
            return "success"
        
        result = func()
        assert result == "success"
    
    def test_decorator_without_args(self):
        """Test decorator without parentheses."""
        @with_retry
        def func():
            return "success"
        
        result = func()
        assert result == "success"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
