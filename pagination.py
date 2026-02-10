"""
Pagination helpers for different pagination strategies.
Each function returns (records, metadata) where metadata varies by strategy.
"""
import base64
import json
import math
from data_generator import generate_records, generate_bookmark_records


def _parse_int(value, default: int) -> int:
    """Safely parse an integer from a query parameter."""
    if value is None:
        return default
    try:
        return max(1, int(value))
    except (ValueError, TypeError):
        return default


def _parse_common_params(req) -> tuple[int, int, int]:
    """Parse common query parameters: totalRecords, pageSize, delay."""
    total_records = _parse_int(req.params.get("totalRecords"), 100)
    page_size = _parse_int(req.params.get("pageSize"), 10)
    delay_ms = _parse_int(req.params.get("delay"), 0)
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
    skip = _parse_int(req.params.get("$skip"), 0)
    skip = max(0, skip)

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
    page = _parse_int(req.params.get("page"), 1)
    total_pages = math.ceil(total_records / page_size)
    page = min(page, total_pages)

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
    limit = _parse_int(req.params.get("limit"), 10)
    limit = min(limit, 500)
    offset = _parse_int(req.params.get("offset"), 0)
    offset = max(0, offset - 1) if offset > 0 else 0  # treat as 0-based

    # Re-read offset as raw to handle 0
    raw_offset = req.params.get("offset")
    if raw_offset is not None:
        try:
            offset = max(0, int(raw_offset))
        except (ValueError, TypeError):
            offset = 0

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
    page = _parse_int(req.params.get("page"), 1)
    total_pages = math.ceil(total_records / page_size)
    page = min(page, total_pages)

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
            offset = cursor_data.get("offset", 0)
        except Exception:
            offset = 0

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
        next_cursor = base64.urlsafe_b64decode if False else base64.urlsafe_b64encode(
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
        if last_job is not None:
            # Next page starts after the last job in the bookmark
            offset = last_job  # job IDs are 1-based, so last_job = offset for next page

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
