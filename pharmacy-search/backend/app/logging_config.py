"""One JSON object per line, on stdout.

Fly collects stdout and forwards it to whatever drain is configured, so the
format of these lines decides whether an incident is answered with a query or
with grep. The default uvicorn output is prose - "INFO: 1.2.3.4:0 - GET
/api/products HTTP/1.1 200 OK" - which cannot be filtered by status, grouped
by path, or joined to anything. These lines can.

Deliberately stdlib-only: structlog and python-json-logger both do this well,
but the runtime image currently ships four dependencies and logging is not
where the fifth should be spent.
"""
import json
import logging
import sys
import time

# Anything on a LogRecord that the stdlib put there. Everything else arrived
# through `extra=` and is a field the caller wanted in the log line, so it
# gets promoted to a top-level key rather than being dropped.
_RESERVED = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            # RFC 3339 in UTC, so it sorts lexically and no drain has to guess
            # a timezone.
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                  + ".%03dZ" % (record.msecs),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        # default=str rather than letting a stray object raise: a log line is
        # never worth taking a request down for.
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # uvicorn installs its own handlers with its own format at import time.
    # Clearing them and letting the records propagate to the root handler is
    # what stops half the output being JSON and half of it not.
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True

    # Silenced rather than reformatted: the request middleware in main.py
    # already emits a line per request, with the timing and request id that
    # uvicorn's access log does not have. Two lines per request would just
    # double the drain's bill.
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False
