"""The log lines are an interface: a drain parses them and alerts off them.

These tests pin the shape - that every line is one JSON object, that the
fields a query would filter on are present and named what they are named, and
that the two things which must never appear (query strings, and a crash caused
by logging itself) do not.
"""
import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.logging_config import JsonFormatter, configure_logging
from app.main import app

client = TestClient(app)


def _format(record: logging.LogRecord) -> dict:
    return json.loads(JsonFormatter().format(record))


def _record(level=logging.INFO, msg="event", **extra) -> logging.LogRecord:
    record = logging.LogRecord("test.logger", level, __file__, 1, msg, (), None)
    record.__dict__.update(extra)
    return record


def test_every_line_is_one_json_object():
    line = JsonFormatter().format(_record())
    assert "\n" not in line
    assert json.loads(line)["event"] == "event"


def test_standard_fields_are_present_and_stable():
    payload = _format(_record(msg="something_happened"))
    assert set(payload) >= {"ts", "level", "logger", "event"}
    assert payload["level"] == "info"
    assert payload["logger"] == "test.logger"
    assert payload["ts"].endswith("Z") and payload["ts"][4] == "-"


def test_extra_fields_are_promoted_to_top_level_keys():
    """A drain filters on `status`, not on a substring of a message."""
    payload = _format(_record(status=404, path="/api/products/9", duration_ms=1.5))
    assert payload["status"] == 404
    assert payload["path"] == "/api/products/9"
    assert payload["duration_ms"] == 1.5


def test_unserialisable_extra_does_not_raise():
    """A log line is never worth taking a request down for."""
    payload = _format(_record(obj=object()))
    assert isinstance(payload["obj"], str)


def test_exceptions_are_captured_as_a_field():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        record = _record(level=logging.ERROR, msg="request_failed")
        record.exc_info = sys.exc_info()
        payload = _format(record)
    assert "ValueError: boom" in payload["exc_info"]


def test_request_is_logged_with_the_fields_an_incident_needs(caplog):
    with caplog.at_level(logging.INFO, logger="pharmacy.request"):
        response = client.get("/api/products", params={"page_size": 1})
    assert response.status_code == 200

    records = [r for r in caplog.records if r.name == "pharmacy.request"]
    assert records, "the request produced no log line"
    payload = _format(records[-1])
    assert payload["event"] == "request"
    assert payload["method"] == "GET"
    assert payload["path"] == "/api/products"
    assert payload["status"] == 200
    assert payload["duration_ms"] >= 0
    assert payload["request_id"]


def test_query_string_is_not_logged(caplog):
    """Search terms are personal data and are already recorded, once, in the
    query log. A token that lands in a URL by mistake must not be captured
    here forever."""
    with caplog.at_level(logging.INFO, logger="pharmacy.request"):
        client.get("/api/search", params={"q": "sensitive-term-xyz"})
    line = JsonFormatter().format(
        [r for r in caplog.records if r.name == "pharmacy.request"][-1]
    )
    assert "sensitive-term-xyz" not in line


def test_request_id_is_echoed_to_the_caller():
    """So a user reporting a problem can quote something findable."""
    response = client.get("/api/health")
    assert response.headers["X-Request-Id"]


def test_upstream_request_id_is_reused():
    """Fly stamps every inbound request. Reusing the id joins this line to the
    edge's own logs instead of starting a parallel universe."""
    response = client.get("/api/health", headers={"fly-request-id": "abc123"})
    assert response.headers["X-Request-Id"] == "abc123"


def test_health_checks_are_logged_at_debug_not_info(caplog):
    """It runs every 15 seconds forever, so at INFO it would be most of the
    drain's volume and none of its value. Asserted both ways round, because
    "no records at all" would otherwise pass this for the wrong reason."""
    with caplog.at_level(logging.DEBUG, logger="pharmacy.request"):
        client.get("/api/health")
    records = [r for r in caplog.records if r.name == "pharmacy.request"]
    assert [r.levelname for r in records] == ["DEBUG"]

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="pharmacy.request"):
        client.get("/api/health")
    assert not [r for r in caplog.records if r.name == "pharmacy.request"]


@pytest.mark.parametrize("path,expected", [
    ("/api/products/999999999", "WARNING"),
])
def test_client_errors_are_logged_above_info(caplog, path, expected):
    """A 404 should be findable without reading every successful request."""
    with caplog.at_level(logging.INFO, logger="pharmacy.request"):
        client.get(path)
    record = [r for r in caplog.records if r.name == "pharmacy.request"][-1]
    assert record.levelname == expected


def test_uvicorn_access_log_is_silenced():
    """Otherwise every request produces two lines, one of them unparseable."""
    configure_logging("INFO")
    access = logging.getLogger("uvicorn.access")
    assert access.handlers == []
    assert access.propagate is False
