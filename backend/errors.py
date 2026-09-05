from __future__ import annotations


class ApiError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message: str, *, details: dict | None = None, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        if status is not None:
            self.status = status


class ValidationError(ApiError):
    status = 400
    code = "validation_error"


class UnauthorizedError(ApiError):
    status = 401
    code = "unauthorized"


class ForbiddenError(ApiError):
    status = 403
    code = "forbidden"


class NotFoundError(ApiError):
    status = 404
    code = "not_found"


class ConflictError(ApiError):
    status = 409
    code = "conflict"


class RateLimitError(ApiError):
    status = 429
    code = "rate_limited"

