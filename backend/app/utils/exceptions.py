"""Domain errors raised by controllers/workflows and mapped to HTTP responses in `app.main`.

Keeping HTTP out of the business layers means workflows can also run from the scheduler or a CLI.
"""


class AppError(Exception):
    status_code = 400

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    status_code = 409


class InvalidRequestError(AppError):
    status_code = 422


class UnauthorizedError(AppError):
    status_code = 401


class RateLimitedError(AppError):
    status_code = 429


class UpstreamError(AppError):
    status_code = 502
