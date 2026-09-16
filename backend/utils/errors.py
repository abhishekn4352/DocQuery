"""
Structured error handling.

Every error the API returns has the same shape:

    {"success": false, "error": {"code": "SOME_CODE", "message": "human text"}}

`AppError` is the one exception type route/service code should raise for any
expected failure (bad input, not found, etc.) with an explicit status_code.
It is registered on the FastAPI app in main.py, so raising it anywhere always
produces the structured body above -- there is no path where an intentional
4xx quietly turns into a 500 (see the old project's Bug #3 in the analysis
report this rewrite is based on).
"""
from __future__ import annotations

import logging

logger = logging.getLogger("docquery")


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


def error_body(code: str, message: str) -> dict:
    return {"success": False, "error": {"code": code, "message": message}}


def not_found(what: str) -> AppError:
    return AppError(404, "NOT_FOUND", f"{what} not found.")
