import logging
from contextvars import ContextVar


# Stores the request ID for the current asynchronous execution context.
request_id_context: ContextVar[str] = ContextVar(
    "request_id",
    default="-"
)


class RequestContextFilter(logging.Filter):
    """
    Adds the current request ID to every log record.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_context.get()
        return True