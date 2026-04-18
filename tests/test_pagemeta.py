"""Tests for the pagemeta strategy (SO-style overflow scenarios)."""
import pytest

from pagination import (
    PaginationError,
    PaginationOverflowError,
    paginate_pagemeta,
)


BASE = "http://localhost:7071"


class TestPagemetaHappyPath:
    def test_first_page(self, make_req):
        body, _ = paginate_pagemeta(
            make_req({"totalRecords": "10", "pageSize": "3", "page": "1"}), BASE
        )
        assert body["metadata"] == {"page": 1, "size": 3, "total": 10}
        assert len(body["data"]) == 3

    def test_last_full_page(self, make_req):
        body, _ = paginate_pagemeta(
            make_req({"totalRecords": "10", "pageSize": "3", "page": "4"}), BASE
        )
        # 10 records, pageSize 3 -> pages 1..4 (last page has 1 record)
        assert body["metadata"]["page"] == 4
        assert len(body["data"]) == 1


class TestPagemetaOverflow:
    OVERSHOOT = {"totalRecords": "10", "pageSize": "3", "page": "5"}

    def test_error_mode_raises_500(self, make_req):
        with pytest.raises(PaginationOverflowError) as exc:
            paginate_pagemeta(make_req({**self.OVERSHOOT, "overflow": "error"}), BASE)
        assert exc.value.status_code == 500
        assert exc.value.body["error"] == "Invalid URL"

    def test_notfound_mode_raises_404(self, make_req):
        with pytest.raises(PaginationOverflowError) as exc:
            paginate_pagemeta(make_req({**self.OVERSHOOT, "overflow": "notfound"}), BASE)
        assert exc.value.status_code == 404

    def test_empty_mode_returns_empty_data(self, make_req):
        body, _ = paginate_pagemeta(
            make_req({**self.OVERSHOOT, "overflow": "empty"}), BASE
        )
        assert body["data"] == []
        assert body["metadata"]["page"] == 5

    def test_clamp_mode_returns_last_page(self, make_req):
        body, _ = paginate_pagemeta(
            make_req({**self.OVERSHOOT, "overflow": "clamp"}), BASE
        )
        # Clamped to page 4 (the last valid page)
        assert body["metadata"]["page"] == 4
        assert len(body["data"]) == 1


class TestPagemetaValidation:
    def test_invalid_overflow_rejected(self, make_req):
        with pytest.raises(PaginationError, match="overflow"):
            paginate_pagemeta(make_req({"overflow": "bogus"}), BASE)

    def test_default_overflow_is_error(self, make_req):
        # Explicit test that omitting overflow reproduces the SO bug.
        with pytest.raises(PaginationOverflowError) as exc:
            paginate_pagemeta(
                make_req({"totalRecords": "10", "pageSize": "3", "page": "99"}), BASE
            )
        assert exc.value.status_code == 500
