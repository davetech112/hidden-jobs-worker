import logging

SENSITIVE_HEADERS = {"x-worker-token", "authorization", "proxy-authorization"}


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        key: "***REDACTED***" if key.lower() in SENSITIVE_HEADERS else value
        for key, value in headers.items()
    }
