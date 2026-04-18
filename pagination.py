"""
Pagination helpers for different pagination strategies.
Each function returns (records, metadata) where metadata varies by strategy.
"""
import base64
import json
import math
from data_generator import generate_records, generate_bookmark_records


class PaginationError(ValueError):
    """Raised when a client supplies invalid pagination input (HTTP 400)."""


class PaginationOverflowError(Exception):
    """
    Raised when a client requests a page beyond the dataset and the endpoint
    is configured to simulate a poorly-behaved API.

    Attributes:
        status_code: HTTP status code to return (e.g. 404, 500).
        body: JSON-serialisable dict to return as the response body.
    """

    def __init__(self, status_code: int, body: dict):
        super().__init__(body.get("error") or f"HTTP {status_code}")
        self.status_code = status_code
        self.body = body


def _parse_positive_int(value, default: int, name: str) -> int:
    """Parse a query parameter that must be >= 1. Returns default if absent."""
    if value is None:
        return default
    try:
        parsed = int(value)
    except (ValueError, TypeError):
        raise PaginationError(f"'{name}' must be an integer, got '{value}'")
    if parsed < 1:
        raise PaginationError(f"'{name}' must be >= 1, got {parsed}")
    return parsed


def _parse_nonneg_int(value, default: int, name: str) -> int:
    """Parse a query parameter that must be >= 0. Returns default if absent."""
    if value is None:
        return default
    try:
        parsed = int(value)
    except (ValueError, TypeError):
        raise PaginationError(f"'{name}' must be an integer, got '{value}'")
    if parsed < 0:
        raise PaginationError(f"'{name}' must be >= 0, got {parsed}")
    return parsed


def _parse_common_params(req) -> tuple[int, int, int]:
    """Parse common query parameters: totalRecords, pageSize, delay."""
    total_records = _parse_positive_int(req.params.get("totalRecords"), 100, "totalRecords")
    page_size = _parse_positive_int(req.params.get("pageSize"), 10, "pageSize")
    delay_ms = _parse_nonneg_int(req.params.get("delay"), 0, "delay")
    # Cap values
    total_records = min(total_records, 10000)
    page_size = min(page_size, 500)
    delay_ms = min(delay_ms, 5000)
    return total_records, page_size, delay_ms


def paginate_nextlink(req, base_url: str) -> tuple[dict, int]:
    """
    OData-style pagination: response body includes @odata.nextLink.

    Query params:
        - totalRecords: total dataset size (default 100)
        - pageSize: records per page (default 10)
        - $skip: records to skip (default 0)
        - delay: simulated delay in ms (default 0)

    Returns:
        (response_body, delay_ms)
    """
    total_records, page_size, delay_ms = _parse_common_params(req)
    skip = _parse_nonneg_int(req.params.get("$skip"), 0, "$skip")

    records = generate_records(skip, page_size, total_records)
    next_skip = skip + page_size

    response = {
        "@odata.context": f"{base_url}/api/paging/nextlink/$metadata",
        "@odata.count": total_records,
        "value": records
    }

    if next_skip < total_records:
        response["@odata.nextLink"] = (
            f"{base_url}/api/paging/nextlink"
            f"?totalRecords={total_records}&pageSize={page_size}"
            f"&$skip={next_skip}&delay={delay_ms}"
        )

    return response, delay_ms


def paginate_header(req, base_url: str) -> tuple[dict, dict, int]:
    """
    Link header pagination: next page URL in response header.

    Query params:
        - totalRecords, pageSize, page, delay

    Returns:
        (response_body, headers_dict, delay_ms)
    """
    total_records, page_size, delay_ms = _parse_common_params(req)
    page = _parse_positive_int(req.params.get("page"), 1, "page")
    total_pages = max(1, math.ceil(total_records / page_size))
    if page > total_pages:
        raise PaginationError(
            f"'page' {page} exceeds total pages {total_pages} "
            f"(totalRecords={total_records}, pageSize={page_size})"
        )

    skip = (page - 1) * page_size
    records = generate_records(skip, page_size, total_records)

    headers = {}
    links = []

    if page < total_pages:
        next_url = (
            f"{base_url}/api/paging/header"
            f"?totalRecords={total_records}&pageSize={page_size}"
            f"&page={page + 1}&delay={delay_ms}"
        )
        links.append(f'<{next_url}>; rel="next"')

    if page > 1:
        prev_url = (
            f"{base_url}/api/paging/header"
            f"?totalRecords={total_records}&pageSize={page_size}"
            f"&page={page - 1}&delay={delay_ms}"
        )
        links.append(f'<{prev_url}>; rel="prev"')

    last_url = (
        f"{base_url}/api/paging/header"
        f"?totalRecords={total_records}&pageSize={page_size}"
        f"&page={total_pages}&delay={delay_ms}"
    )
    links.append(f'<{last_url}>; rel="last"')

    first_url = (
        f"{base_url}/api/paging/header"
        f"?totalRecords={total_records}&pageSize={page_size}"
        f"&page=1&delay={delay_ms}"
    )
    links.append(f'<{first_url}>; rel="first"')

    if links:
        headers["Link"] = ", ".join(links)

    response = {
        "data": records,
        "page": page,
        "pageSize": page_size,
        "totalPages": total_pages,
        "totalRecords": total_records
    }

    return response, headers, delay_ms


def paginate_offset(req, base_url: str) -> tuple[dict, int]:
    """
    Offset/Limit pagination.

    Query params:
        - totalRecords, offset, limit, delay

    Returns:
        (response_body, delay_ms)
    """
    total_records, _, delay_ms = _parse_common_params(req)
    limit = min(_parse_positive_int(req.params.get("limit"), 10, "limit"), 500)
    offset = _parse_nonneg_int(req.params.get("offset"), 0, "offset")

    records = generate_records(offset, limit, total_records)
    next_offset = offset + limit
    has_more = next_offset < total_records

    response = {
        "data": records,
        "offset": offset,
        "limit": limit,
        "totalRecords": total_records,
        "hasMore": has_more
    }

    if has_more:
        response["nextOffset"] = next_offset
        response["nextUrl"] = (
            f"{base_url}/api/paging/offset"
            f"?totalRecords={total_records}&limit={limit}"
            f"&offset={next_offset}&delay={delay_ms}"
        )

    return response, delay_ms


def paginate_page_number(req, base_url: str) -> tuple[dict, int]:
    """
    Page number pagination.

    Query params:
        - totalRecords, pageSize, page, delay

    Returns:
        (response_body, delay_ms)
    """
    total_records, page_size, delay_ms = _parse_common_params(req)
    page = _parse_positive_int(req.params.get("page"), 1, "page")
    total_pages = max(1, math.ceil(total_records / page_size))
    if page > total_pages:
        raise PaginationError(
            f"'page' {page} exceeds total pages {total_pages} "
            f"(totalRecords={total_records}, pageSize={page_size})"
        )

    skip = (page - 1) * page_size
    records = generate_records(skip, page_size, total_records)

    response = {
        "data": records,
        "pagination": {
            "currentPage": page,
            "pageSize": page_size,
            "totalPages": total_pages,
            "totalRecords": total_records,
            "hasNextPage": page < total_pages,
            "hasPreviousPage": page > 1
        }
    }

    if page < total_pages:
        response["pagination"]["nextPageUrl"] = (
            f"{base_url}/api/paging/pagenumber"
            f"?totalRecords={total_records}&pageSize={page_size}"
            f"&page={page + 1}&delay={delay_ms}"
        )

    if page > 1:
        response["pagination"]["previousPageUrl"] = (
            f"{base_url}/api/paging/pagenumber"
            f"?totalRecords={total_records}&pageSize={page_size}"
            f"&page={page - 1}&delay={delay_ms}"
        )

    return response, delay_ms


def paginate_cursor(req, base_url: str) -> tuple[dict, int]:
    """
    Cursor/continuation token pagination.

    The cursor is a base64-encoded JSON object containing the offset.

    Query params:
        - totalRecords, pageSize, cursor, delay

    Returns:
        (response_body, delay_ms)
    """
    total_records, page_size, delay_ms = _parse_common_params(req)

    cursor = req.params.get("cursor")
    offset = 0

    if cursor:
        try:
            decoded = base64.urlsafe_b64decode(cursor).decode("utf-8")
            cursor_data = json.loads(decoded)
            offset = int(cursor_data.get("offset", 0))
            if offset < 0:
                raise ValueError("negative offset in cursor")
        except Exception as e:
            raise PaginationError(f"Invalid 'cursor' token: {e}")

    records = generate_records(offset, page_size, total_records)
    next_offset = offset + page_size
    has_more = next_offset < total_records

    response = {
        "data": records,
        "pageSize": page_size,
        "totalRecords": total_records,
        "hasMore": has_more
    }

    if has_more:
        next_cursor_data = json.dumps({"offset": next_offset, "ts": "2025-01-01T00:00:00Z"})
        next_cursor = base64.urlsafe_b64encode(
            next_cursor_data.encode("utf-8")
        ).decode("utf-8")
        response["continuationToken"] = next_cursor
        response["nextUrl"] = (
            f"{base_url}/api/paging/cursor"
            f"?totalRecords={total_records}&pageSize={page_size}"
            f"&cursor={next_cursor}&delay={delay_ms}"
        )

    return response, delay_ms


def _build_bookmark_xml(first_job: int, last_job: int, first_site: str, last_site: str) -> str:
    """
    Build an XML bookmark string matching the ERP-style format.
    Columns: job, suffix, site_ref. Sort: ascending on all.
    <F> = first row keys, <L> = last row keys.
    """
    return (
        "<B>"
        "<P><p>job</p><p>suffix</p><p>site_ref</p></P>"
        "<D><f>false</f><f>false</f><f>false</f></D>"
        f"<F><v> {first_job}</v><v>0</v><v>{first_site}</v></F>"
        f"<L><v> {last_job}</v><v>0</v><v>{last_site}</v></L>"
        "</B>"
    )


def _parse_bookmark_xml(bookmark: str) -> int | None:
    """
    Parse the <L> (last) job value from a bookmark XML string
    to determine where the next page should start.
    Returns the last job number, or None if parsing fails.
    """
    import re
    # Extract the <L> element's first <v> value (the job number)
    match = re.search(r"<L><v>\s*(\d+)", bookmark)
    if match:
        return int(match.group(1))
    return None


def paginate_bookmark(req, base_url: str) -> tuple[dict, int]:
    """
    Bookmark/ERP-style pagination.

    The response includes an XML-encoded Bookmark string and a
    MoreRowsExist flag. Clients pass the Bookmark value in the
    next request to continue paging.

    Query params:
        - totalRecords: total dataset size (default 100)
        - pageSize: records per page (default 10)
        - bookmark: XML bookmark from previous response (default: none)
        - delay: simulated delay in ms (default 0)

    Returns:
        (response_body, delay_ms)
    """
    total_records, page_size, delay_ms = _parse_common_params(req)

    bookmark = req.params.get("bookmark")
    offset = 0

    if bookmark:
        # Decode if URL-encoded, then parse
        from urllib.parse import unquote
        decoded_bookmark = unquote(bookmark)
        last_job = _parse_bookmark_xml(decoded_bookmark)
        if last_job is None:
            raise PaginationError(
                "Invalid 'bookmark' value: could not extract last row key from XML. "
                "Expected a <B>...<L><v> N</v>...</L></B> structure."
            )
        # Next page starts after the last job in the bookmark.
        # Job IDs are 1-based and contiguous, so last_job == next offset.
        offset = last_job

    records = generate_bookmark_records(offset, page_size, total_records)
    next_offset = offset + page_size
    has_more = next_offset < total_records

    # Build bookmark from first and last records in this page
    if records:
        first_rec = records[0]
        last_rec = records[-1]
        bookmark_xml = _build_bookmark_xml(
            int(first_rec["job"]), int(last_rec["job"]),
            first_rec["site_ref"], last_rec["site_ref"]
        )
    else:
        bookmark_xml = ""

    response = {
        "Items": records,
        "Bookmark": bookmark_xml,
        "MoreRowsExist": has_more,
        "Success": True,
        "Message": None,
    }

    return response, delay_ms


def paginate_range(req, base_url: str) -> tuple[dict, int]:
    """
    Range-based pagination.

    Supports two URL styles:
      1. Combined:  ?range=0-99   (single param with start-stop)
      2. Separate:  ?start=0&stop=99  (two params)

    If 'start' and 'stop' are provided, they take precedence over 'range'.

    Query params:
        - totalRecords: total dataset size (default 100)
        - range: 'start-stop' inclusive range, e.g. '0-99' (default '0-9')
        - start: start index, 0-based (alternative to range)
        - stop: stop index, inclusive (alternative to range)
        - delay: simulated delay in ms (default 0)

    Returns:
        (response_body, delay_ms)
    """
    total_records, _, delay_ms = _parse_common_params(req)

    # Support both ?start=0&stop=99 and ?range=0-99
    raw_start = req.params.get("start")
    raw_stop = req.params.get("stop")

    if raw_start is not None and raw_stop is not None:
        range_start = _parse_nonneg_int(raw_start, 0, "start")
        range_stop = _parse_nonneg_int(raw_stop, 0, "stop")
        if range_stop < range_start:
            raise PaginationError(
                f"'stop' ({range_stop}) must be >= 'start' ({range_start})"
            )
    else:
        range_param = req.params.get("range", "0-9")
        try:
            parts = range_param.split("-")
            if len(parts) != 2:
                raise ValueError("expected 'start-stop' format")
            range_start = int(parts[0])
            range_stop = int(parts[1])
            if range_start < 0 or range_stop < range_start:
                raise ValueError("start must be >= 0 and stop >= start")
        except ValueError as e:
            raise PaginationError(
                f"Invalid 'range' value '{range_param}': {e}. Expected 'start-stop', e.g. '0-99'."
            )

    page_size = range_stop - range_start + 1
    records = generate_records(range_start, page_size, total_records)
    next_start = range_stop + 1
    has_more = next_start < total_records

    response = {
        "data": records,
        "range": f"{range_start}-{range_stop}",
        "start": range_start,
        "stop": range_stop,
        "totalRecords": total_records,
        "hasMore": has_more,
    }

    if has_more:
        next_stop = min(next_start + page_size - 1, total_records - 1)
        response["nextRange"] = f"{next_start}-{next_stop}"
        response["nextStart"] = next_start
        response["nextStop"] = next_stop
        response["nextUrl"] = (
            f"{base_url}/api/paging/range"
            f"?totalRecords={total_records}"
            f"&range={next_start}-{next_stop}&delay={delay_ms}"
        )

    return response, delay_ms


# Allowed values for the `overflow` query parameter on paginate_pagemeta.
_PAGEMETA_OVERFLOW_MODES = {"error", "empty", "clamp", "notfound"}


def paginate_pagemeta(req, base_url: str) -> tuple[dict, int]:
    """
    Page-number pagination that mirrors the real-world API shape:

        {
          "data": [ ... ],
          "metadata": { "page": 1, "size": 1000, "total": 3128 }
        }

    Reproduces the common Fabric/ADF problem where an API exposes `total`
    in metadata but has no `hasNext`/`nextUrl` field and misbehaves on
    out-of-range pages (see
    https://stackoverflow.com/questions/79926567).

    Query params:
        - totalRecords: total dataset size (default 100)
        - pageSize:     rows per page; surfaced as metadata.size (default 10)
        - page:         1-based page number (default 1)
        - overflow:     behaviour when page > ceil(totalRecords / pageSize).
                        One of:
                          * 'error'    -> HTTP 500 with a fake "Invalid URL"
                                          body (matches the SO scenario).
                          * 'empty'    -> HTTP 200 with "data": [] and the
                                          requested page in metadata.
                          * 'clamp'    -> HTTP 200 returning the last valid
                                          page (silent — hardest to detect).
                          * 'notfound' -> HTTP 404 with a structured error.
                        Default: 'error'.
        - delay:        simulated delay in ms (default 0)

    Returns:
        (response_body, delay_ms)

    Raises:
        PaginationOverflowError when overflow=='error' or overflow=='notfound'
        and the requested page is out of range.
    """
    total_records, page_size, delay_ms = _parse_common_params(req)
    page = _parse_positive_int(req.params.get("page"), 1, "page")

    overflow_mode = (req.params.get("overflow") or "error").lower()
    if overflow_mode not in _PAGEMETA_OVERFLOW_MODES:
        raise PaginationError(
            f"'overflow' must be one of {sorted(_PAGEMETA_OVERFLOW_MODES)}, "
            f"got '{overflow_mode}'"
        )

    total_pages = max(1, math.ceil(total_records / page_size))

    if page > total_pages:
        if overflow_mode == "error":
            raise PaginationOverflowError(
                status_code=500,
                body={
                    "error": "Invalid URL",
                    "message": (
                        f"Page {page} is out of range. This endpoint simulates "
                        f"a poorly-behaved API that fails hard on overflow."
                    ),
                },
            )
        if overflow_mode == "notfound":
            raise PaginationOverflowError(
                status_code=404,
                body={
                    "error": "Not Found",
                    "message": (
                        f"Page {page} exceeds total pages {total_pages} "
                        f"(totalRecords={total_records}, pageSize={page_size})."
                    ),
                },
            )
        if overflow_mode == "clamp":
            page = total_pages
        # overflow_mode == "empty": fall through with empty data.

    skip = (page - 1) * page_size
    if skip >= total_records:
        records = []
    else:
        records = generate_records(skip, page_size, total_records)

    return {
        "data": records,
        "metadata": {
            "page": page,
            "size": page_size,
            "total": total_records,
        },
    }, delay_ms
