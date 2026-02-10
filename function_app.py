"""
Fabric Paging Simulator - Azure Function App

Simulates REST API pagination patterns for testing Microsoft Fabric
Data Pipeline Copy Activity pagination rules.

Endpoints:
    GET /api/paging/nextlink   - OData-style @odata.nextLink in response body
    GET /api/paging/header     - Link header with rel="next"
    GET /api/paging/offset     - Offset/Limit query parameter pagination
    GET /api/paging/pagenumber - Page number query parameter pagination
    GET /api/paging/cursor     - Cursor/continuation token pagination
    GET /api/info              - API info and endpoint documentation
"""
import json
import time
import logging
import azure.functions as func

from pagination import (
    paginate_nextlink,
    paginate_header,
    paginate_offset,
    paginate_page_number,
    paginate_cursor,
)

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


def _get_base_url(req: func.HttpRequest) -> str:
    """Extract the base URL from the incoming request."""
    url = req.url
    # Strip the path to get scheme + host
    # e.g., http://localhost:7071/api/paging/nextlink -> http://localhost:7071
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _json_response(body: dict, status_code: int = 200, headers: dict = None) -> func.HttpResponse:
    """Create a JSON HttpResponse."""
    resp_headers = {"Content-Type": "application/json"}
    if headers:
        resp_headers.update(headers)
    return func.HttpResponse(
        body=json.dumps(body, indent=2),
        status_code=status_code,
        headers=resp_headers
    )


def _apply_delay(delay_ms: int):
    """Apply simulated delay if configured."""
    if delay_ms > 0:
        time.sleep(delay_ms / 1000.0)


# ─────────────────────────────────────────────
# Info endpoint
# ─────────────────────────────────────────────

@app.route(route="info", methods=["GET"])
def info(req: func.HttpRequest) -> func.HttpResponse:
    """Returns API documentation and available endpoints."""
    base_url = _get_base_url(req)
    logging.info("Info endpoint called")

    doc = {
        "name": "Fabric Paging Simulator",
        "description": (
            "Simulates REST API pagination patterns for testing "
            "Microsoft Fabric Data Pipeline Copy Activity pagination rules."
        ),
        "version": "1.0.0",
        "endpoints": {
            "nextlink": {
                "url": f"{base_url}/api/paging/nextlink",
                "description": "OData-style pagination with @odata.nextLink in response body",
                "params": {
                    "totalRecords": "Total records in dataset (default: 100, max: 10000)",
                    "pageSize": "Records per page (default: 10, max: 500)",
                    "$skip": "Number of records to skip (default: 0)",
                    "delay": "Simulated response delay in ms (default: 0, max: 5000)"
                },
                "paginationRule": "Body: $.@odata.nextLink → use as absolute URL for next request"
            },
            "header": {
                "url": f"{base_url}/api/paging/header",
                "description": "Link header pagination with rel='next'",
                "params": {
                    "totalRecords": "Total records in dataset (default: 100, max: 10000)",
                    "pageSize": "Records per page (default: 10, max: 500)",
                    "page": "Current page number (default: 1)",
                    "delay": "Simulated response delay in ms (default: 0, max: 5000)"
                },
                "paginationRule": "Header: Link → parse rel='next' URL"
            },
            "offset": {
                "url": f"{base_url}/api/paging/offset",
                "description": "Offset/Limit query parameter pagination",
                "params": {
                    "totalRecords": "Total records in dataset (default: 100, max: 10000)",
                    "limit": "Records per page (default: 10, max: 500)",
                    "offset": "Starting record offset, 0-based (default: 0)",
                    "delay": "Simulated response delay in ms (default: 0, max: 5000)"
                },
                "paginationRule": "Body: $.nextUrl → use as absolute URL, or increment offset by limit"
            },
            "pagenumber": {
                "url": f"{base_url}/api/paging/pagenumber",
                "description": "Page number query parameter pagination",
                "params": {
                    "totalRecords": "Total records in dataset (default: 100, max: 10000)",
                    "pageSize": "Records per page (default: 10, max: 500)",
                    "page": "Current page number (default: 1)",
                    "delay": "Simulated response delay in ms (default: 0, max: 5000)"
                },
                "paginationRule": "Body: $.pagination.nextPageUrl → use as absolute URL, or increment page"
            },
            "cursor": {
                "url": f"{base_url}/api/paging/cursor",
                "description": "Cursor/continuation token pagination",
                "params": {
                    "totalRecords": "Total records in dataset (default: 100, max: 10000)",
                    "pageSize": "Records per page (default: 10, max: 500)",
                    "cursor": "Continuation token from previous response (default: none)",
                    "delay": "Simulated response delay in ms (default: 0, max: 5000)"
                },
                "paginationRule": "Body: $.continuationToken → pass as 'cursor' query param in next request"
            }
        },
        "examples": {
            "nextlink_first_page": f"{base_url}/api/paging/nextlink?totalRecords=50&pageSize=10",
            "header_page_2": f"{base_url}/api/paging/header?totalRecords=50&pageSize=10&page=2",
            "offset_with_delay": f"{base_url}/api/paging/offset?totalRecords=100&limit=25&offset=0&delay=500",
            "pagenumber_small": f"{base_url}/api/paging/pagenumber?totalRecords=30&pageSize=10",
            "cursor_start": f"{base_url}/api/paging/cursor?totalRecords=50&pageSize=10"
        }
    }

    return _json_response(doc)


# ─────────────────────────────────────────────
# 1. OData NextLink pagination
# ─────────────────────────────────────────────

@app.route(route="paging/nextlink", methods=["GET"])
def paging_nextlink(req: func.HttpRequest) -> func.HttpResponse:
    """
    OData-style pagination.
    Returns @odata.nextLink in the response body when more pages exist.
    """
    logging.info("NextLink pagination endpoint called")
    base_url = _get_base_url(req)

    try:
        response, delay_ms = paginate_nextlink(req, base_url)
        _apply_delay(delay_ms)
        return _json_response(response)
    except Exception as e:
        logging.error(f"Error in nextlink pagination: {e}")
        return _json_response({"error": str(e)}, status_code=500)


# ─────────────────────────────────────────────
# 2. Link Header pagination
# ─────────────────────────────────────────────

@app.route(route="paging/header", methods=["GET"])
def paging_header(req: func.HttpRequest) -> func.HttpResponse:
    """
    Link header pagination.
    Returns next/prev/first/last URLs in the Link response header.
    """
    logging.info("Header pagination endpoint called")
    base_url = _get_base_url(req)

    try:
        response, headers, delay_ms = paginate_header(req, base_url)
        _apply_delay(delay_ms)
        return _json_response(response, headers=headers)
    except Exception as e:
        logging.error(f"Error in header pagination: {e}")
        return _json_response({"error": str(e)}, status_code=500)


# ─────────────────────────────────────────────
# 3. Offset/Limit pagination
# ─────────────────────────────────────────────

@app.route(route="paging/offset", methods=["GET"])
def paging_offset(req: func.HttpRequest) -> func.HttpResponse:
    """
    Offset/Limit pagination.
    Uses offset and limit query parameters to control paging.
    """
    logging.info("Offset pagination endpoint called")
    base_url = _get_base_url(req)

    try:
        response, delay_ms = paginate_offset(req, base_url)
        _apply_delay(delay_ms)
        return _json_response(response)
    except Exception as e:
        logging.error(f"Error in offset pagination: {e}")
        return _json_response({"error": str(e)}, status_code=500)


# ─────────────────────────────────────────────
# 4. Page Number pagination
# ─────────────────────────────────────────────

@app.route(route="paging/pagenumber", methods=["GET"])
def paging_pagenumber(req: func.HttpRequest) -> func.HttpResponse:
    """
    Page number pagination.
    Uses page and pageSize query parameters.
    """
    logging.info("Page number pagination endpoint called")
    base_url = _get_base_url(req)

    try:
        response, delay_ms = paginate_page_number(req, base_url)
        _apply_delay(delay_ms)
        return _json_response(response)
    except Exception as e:
        logging.error(f"Error in page number pagination: {e}")
        return _json_response({"error": str(e)}, status_code=500)


# ─────────────────────────────────────────────
# 5. Cursor/Continuation Token pagination
# ─────────────────────────────────────────────

@app.route(route="paging/cursor", methods=["GET"])
def paging_cursor(req: func.HttpRequest) -> func.HttpResponse:
    """
    Cursor/continuation token pagination.
    Returns a continuationToken in the response body for fetching the next page.
    """
    logging.info("Cursor pagination endpoint called")
    base_url = _get_base_url(req)

    try:
        response, delay_ms = paginate_cursor(req, base_url)
        _apply_delay(delay_ms)
        return _json_response(response)
    except Exception as e:
        logging.error(f"Error in cursor pagination: {e}")
        return _json_response({"error": str(e)}, status_code=500)
