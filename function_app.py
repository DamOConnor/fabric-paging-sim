"""
Fabric Paging Simulator - Azure Function App

Thin HTTP layer over the pagination strategies declared in
`pagination.STRATEGIES`. Adding a new endpoint only requires appending to
that registry - no edits here are needed.
"""
import json
import logging
import time
from urllib.parse import urlparse

import azure.functions as func

from pagination import (
    PaginationError,
    PaginationOverflowError,
    STRATEGIES,
    Strategy,
)

API_VERSION = "1.3.0"

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_base_url(req: func.HttpRequest) -> str:
    """Extract scheme://host from the incoming request URL."""
    parsed = urlparse(req.url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _json_response(body: dict, status_code: int = 200, headers: dict | None = None) -> func.HttpResponse:
    """Serialise body to JSON and return as an HttpResponse."""
    resp_headers = {"Content-Type": "application/json"}
    if headers:
        resp_headers.update(headers)
    return func.HttpResponse(
        body=json.dumps(body, indent=2),
        status_code=status_code,
        headers=resp_headers,
    )


def _apply_delay(delay_ms: int) -> None:
    if delay_ms > 0:
        time.sleep(delay_ms / 1000.0)


# ---------------------------------------------------------------------------
# Generic strategy handler - one try/except pattern shared across endpoints
# ---------------------------------------------------------------------------

def _make_handler(strategy: Strategy):
    """Build an Azure Functions HTTP handler for a single pagination strategy."""

    def handler(req: func.HttpRequest) -> func.HttpResponse:
        logging.info("%s pagination endpoint called", strategy.name)
        base_url = _get_base_url(req)
        try:
            body, delay_ms, headers = strategy.invoke(req, base_url)
            _apply_delay(delay_ms)
            return _json_response(body, headers=headers or None)
        except PaginationOverflowError as e:
            return _json_response(e.body, status_code=e.status_code)
        except PaginationError as e:
            return _json_response({"error": str(e)}, status_code=400)
        except Exception as e:  # noqa: BLE001 - surface unexpected errors as 500
            logging.exception("Unhandled error in %s", strategy.name)
            return _json_response({"error": str(e)}, status_code=500)

    handler.__name__ = f"paging_{strategy.name}"
    handler.__doc__ = strategy.description
    return handler


# Register one HTTP route per strategy.
for _strategy in STRATEGIES:
    app.route(route=_strategy.route, methods=["GET"])(_make_handler(_strategy))


# ---------------------------------------------------------------------------
# /api/info - auto-generated from the registry
# ---------------------------------------------------------------------------

@app.route(route="info", methods=["GET"])
def info(req: func.HttpRequest) -> func.HttpResponse:
    """Return API documentation derived from the strategy registry."""
    base_url = _get_base_url(req)
    logging.info("Info endpoint called")

    endpoints = {
        s.name: {
            "url": f"{base_url}/api/{s.route}",
            "description": s.description,
            "params": dict(s.params),
            "paginationRule": s.pagination_rule,
        }
        for s in STRATEGIES
    }

    examples = {
        f"{s.name}_example": f"{base_url}/api/{s.route}{s.example_query}"
        for s in STRATEGIES
        if s.example_query
    }
    # Keep the well-known SO-repro examples visible.
    pagemeta_url = f"{base_url}/api/paging/pagemeta"
    examples["pagemeta_overflow_error"] = f"{pagemeta_url}?totalRecords=10&pageSize=3&page=5&overflow=error"
    examples["pagemeta_overflow_empty"] = f"{pagemeta_url}?totalRecords=10&pageSize=3&page=5&overflow=empty"

    doc = {
        "name": "Fabric Paging Simulator",
        "description": (
            "Simulates REST API pagination patterns for testing "
            "Microsoft Fabric Data Pipeline Copy Activity pagination rules."
        ),
        "version": API_VERSION,
        "endpoints": endpoints,
        "examples": examples,
    }
    return _json_response(doc)
