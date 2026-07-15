"""Error envelope helpers."""
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """An error that maps directly to the spec's error envelope."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def envelope(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def error_response(status: int, code: str, message: str, headers=None) -> JSONResponse:
    return JSONResponse(
        status_code=status, content=envelope(code, message), headers=headers
    )
