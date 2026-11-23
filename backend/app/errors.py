"""Uniform error body: {"error": {"code": ..., "message": ...}} (frontend lib/api.ts)."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def not_found(what: str) -> ApiError:
    return ApiError(404, "NOT_FOUND", f"{what} not found")


def forbidden(message: str = "You do not have permission to do this") -> ApiError:
    return ApiError(403, "FORBIDDEN", message)


def conflict(message: str, code: str = "CONFLICT") -> ApiError:
    return ApiError(409, code, message)


def bad_request(message: str, code: str = "BAD_REQUEST") -> ApiError:
    return ApiError(400, code, message)


def _body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


_HTTP_CODES = {400: "BAD_REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND",
               405: "METHOD_NOT_ALLOWED", 409: "CONFLICT", 413: "FILE_TOO_LARGE", 422: "VALIDATION_ERROR"}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status, content=_body(exc.code, exc.message))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(_HTTP_CODES.get(exc.status_code, "ERROR"), str(exc.detail)),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", []) if p not in ("body", "query", "path"))
        msg = first.get("msg", "Invalid request")
        return JSONResponse(status_code=422, content=_body("VALIDATION_ERROR", f"{field}: {msg}" if field else msg))
