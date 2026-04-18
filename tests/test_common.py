"""Tests for common parameter parsing and error types."""
import pytest

from pagination import (
    PaginationError,
    PaginationOverflowError,
    _parse_nonneg_int,
    _parse_positive_int,
    _parse_common_params,
)


class TestParsePositiveInt:
    def test_default_when_none(self):
        assert _parse_positive_int(None, 10, "x") == 10

    def test_valid_value(self):
        assert _parse_positive_int("5", 10, "x") == 5

    def test_zero_rejected(self):
        with pytest.raises(PaginationError, match="must be >= 1"):
            _parse_positive_int("0", 10, "pageSize")

    def test_negative_rejected(self):
        with pytest.raises(PaginationError, match="must be >= 1"):
            _parse_positive_int("-1", 10, "x")

    def test_non_integer_rejected(self):
        with pytest.raises(PaginationError, match="must be an integer"):
            _parse_positive_int("abc", 10, "x")


class TestParseNonnegInt:
    def test_default_when_none(self):
        assert _parse_nonneg_int(None, 0, "x") == 0

    def test_zero_accepted(self):
        assert _parse_nonneg_int("0", 5, "delay") == 0

    def test_negative_rejected(self):
        with pytest.raises(PaginationError, match="must be >= 0"):
            _parse_nonneg_int("-10", 0, "$skip")

    def test_non_integer_rejected(self):
        with pytest.raises(PaginationError, match="must be an integer"):
            _parse_nonneg_int("xyz", 0, "offset")


class TestParseCommonParams:
    def test_defaults(self, make_req):
        total, size, delay = _parse_common_params(make_req())
        assert (total, size, delay) == (100, 10, 0)

    def test_caps(self, make_req):
        req = make_req({"totalRecords": "50000", "pageSize": "10000", "delay": "99999"})
        total, size, delay = _parse_common_params(req)
        assert total == 10000
        assert size == 500
        assert delay == 5000


class TestPaginationOverflowError:
    def test_stores_status_and_body(self):
        err = PaginationOverflowError(status_code=404, body={"error": "Not Found"})
        assert err.status_code == 404
        assert err.body == {"error": "Not Found"}
