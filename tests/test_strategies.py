"""Tests for each pagination strategy (happy path + validation)."""
import base64
import json

import pytest

from pagination import (
    PaginationError,
    paginate_bookmark,
    paginate_cursor,
    paginate_header,
    paginate_nextlink,
    paginate_offset,
    paginate_page_number,
    paginate_range,
)


BASE = "http://localhost:7071"


class TestNextLink:
    def test_first_page_has_next_link(self, make_req):
        body, delay = paginate_nextlink(make_req({"totalRecords": "20", "pageSize": "10"}), BASE)
        assert len(body["value"]) == 10
        assert body["@odata.count"] == 20
        assert "$skip=10" in body["@odata.nextLink"]
        assert delay == 0

    def test_last_page_no_next_link(self, make_req):
        body, _ = paginate_nextlink(
            make_req({"totalRecords": "20", "pageSize": "10", "$skip": "10"}), BASE
        )
        assert len(body["value"]) == 10
        assert "@odata.nextLink" not in body

    def test_negative_skip_rejected(self, make_req):
        with pytest.raises(PaginationError):
            paginate_nextlink(make_req({"$skip": "-1"}), BASE)

    def test_pagesize_zero_rejected(self, make_req):
        with pytest.raises(PaginationError):
            paginate_nextlink(make_req({"pageSize": "0"}), BASE)


class TestHeader:
    def test_middle_page_has_prev_and_next(self, make_req):
        body, headers, _ = paginate_header(
            make_req({"totalRecords": "30", "pageSize": "10", "page": "2"}), BASE
        )
        assert body["page"] == 2
        assert body["totalPages"] == 3
        assert 'rel="next"' in headers["Link"]
        assert 'rel="prev"' in headers["Link"]

    def test_page_out_of_range_rejected(self, make_req):
        with pytest.raises(PaginationError, match="exceeds total pages"):
            paginate_header(make_req({"totalRecords": "10", "pageSize": "10", "page": "999"}), BASE)


class TestOffset:
    def test_offset_zero_is_first_page(self, make_req):
        body, _ = paginate_offset(
            make_req({"totalRecords": "20", "limit": "5", "offset": "0"}), BASE
        )
        assert body["offset"] == 0
        assert len(body["data"]) == 5
        assert body["nextOffset"] == 5

    def test_final_offset_has_no_more(self, make_req):
        body, _ = paginate_offset(
            make_req({"totalRecords": "10", "limit": "10", "offset": "0"}), BASE
        )
        assert body["hasMore"] is False
        assert "nextUrl" not in body

    def test_negative_offset_rejected(self, make_req):
        with pytest.raises(PaginationError):
            paginate_offset(make_req({"offset": "-5"}), BASE)


class TestPageNumber:
    def test_page_one(self, make_req):
        body, _ = paginate_page_number(
            make_req({"totalRecords": "30", "pageSize": "10", "page": "1"}), BASE
        )
        assert body["pagination"]["currentPage"] == 1
        assert body["pagination"]["hasNextPage"] is True

    def test_last_page(self, make_req):
        body, _ = paginate_page_number(
            make_req({"totalRecords": "30", "pageSize": "10", "page": "3"}), BASE
        )
        assert body["pagination"]["hasNextPage"] is False
        assert "nextPageUrl" not in body["pagination"]

    def test_page_zero_rejected(self, make_req):
        with pytest.raises(PaginationError):
            paginate_page_number(make_req({"page": "0"}), BASE)


class TestCursor:
    def test_start_cursor(self, make_req):
        body, _ = paginate_cursor(make_req({"totalRecords": "30", "pageSize": "10"}), BASE)
        assert body["hasMore"] is True
        assert "continuationToken" in body

    def test_follow_cursor(self, make_req):
        first, _ = paginate_cursor(make_req({"totalRecords": "30", "pageSize": "10"}), BASE)
        token = first["continuationToken"]
        second, _ = paginate_cursor(
            make_req({"totalRecords": "30", "pageSize": "10", "cursor": token}), BASE
        )
        # verify offset encoded in token was honoured
        decoded = json.loads(base64.urlsafe_b64decode(token).decode("utf-8"))
        assert decoded["offset"] == 10
        assert second["data"][0]["id"] == 11

    def test_invalid_cursor_rejected(self, make_req):
        with pytest.raises(PaginationError, match="Invalid 'cursor'"):
            paginate_cursor(make_req({"cursor": "garbage!!!"}), BASE)


class TestBookmark:
    def test_first_page(self, make_req):
        body, _ = paginate_bookmark(make_req({"totalRecords": "20", "pageSize": "10"}), BASE)
        assert len(body["Items"]) == 10
        assert body["MoreRowsExist"] is True
        assert body["Bookmark"].startswith("<B>")

    def test_invalid_bookmark_rejected(self, make_req):
        with pytest.raises(PaginationError, match="Invalid 'bookmark'"):
            paginate_bookmark(make_req({"bookmark": "garbage"}), BASE)


class TestRange:
    def test_range_param(self, make_req):
        body, _ = paginate_range(make_req({"totalRecords": "100", "range": "0-9"}), BASE)
        assert body["range"] == "0-9"
        assert len(body["data"]) == 10
        assert body["nextStart"] == 10

    def test_start_stop_params(self, make_req):
        body, _ = paginate_range(
            make_req({"totalRecords": "100", "start": "5", "stop": "14"}), BASE
        )
        assert body["start"] == 5
        assert body["stop"] == 14
        assert len(body["data"]) == 10

    def test_malformed_range_rejected(self, make_req):
        with pytest.raises(PaginationError):
            paginate_range(make_req({"range": "not-a-range"}), BASE)

    def test_stop_before_start_rejected(self, make_req):
        with pytest.raises(PaginationError):
            paginate_range(make_req({"start": "10", "stop": "5"}), BASE)
