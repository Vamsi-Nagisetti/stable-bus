import logging
import time
import uuid
from typing import Any, Callable

from core.request_context import request_id_context


logger = logging.getLogger("stablebus.middleware.request")


class RequestLoggingMiddleware:

    def __init__(self, app: Callable):
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable,
        send: Callable
    ):

        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid7())

        context_token = request_id_context.set(request_id)

        method = scope["method"]
        path = scope["path"]

        start_time = time.perf_counter()
        status_code = None

        async def send_wrapper(message: dict[str, Any]):

            nonlocal status_code

            if message["type"] == "http.response.start":

                status_code = message["status"]

                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ]

                headers.append(
                    (b"x-request-id", request_id.encode("utf-8"))
                )

                message = {**message, "headers": headers}

            await send(message)

        try:

            await self.app(scope, receive, send_wrapper)

            duration_ms = (
                time.perf_counter() - start_time
            ) * 1000

            logger.info(
                "Request completed | method=%s | path=%s "
                "| status=%s | duration_ms=%.2f",
                method,
                path,
                status_code,
                duration_ms
            )

        except Exception:

            duration_ms = (
                time.perf_counter() - start_time
            ) * 1000

            logger.exception(
                "Request failed | method=%s | path=%s "
                "| status=%s | duration_ms=%.2f",
                method,
                path,
                status_code,
                duration_ms
            )

            raise

        finally:

            request_id_context.reset(context_token)