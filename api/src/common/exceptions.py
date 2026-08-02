"""Custom exception hierarchy.

Every exception maps to a specific HTTP status code so the error-handling
middleware in `handler.py` can translate it into the standardized response
envelope without each resource module needing to know about HTTP semantics.
"""


class ApiError(Exception):
    """Base class for all handled API errors."""

    status_code = 500
    error_code = "internal_error"

    def __init__(self, message: str = None, details: dict = None):
        self.message = message or "An unexpected error occurred."
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(ApiError):
    status_code = 400
    error_code = "validation_error"

    def __init__(self, message: str = "Request failed validation.", details: dict = None):
        super().__init__(message, details)


class NotFoundError(ApiError):
    status_code = 404
    error_code = "not_found"

    def __init__(self, message: str = "Resource not found.", details: dict = None):
        super().__init__(message, details)


class ConflictError(ApiError):
    status_code = 409
    error_code = "conflict"

    def __init__(self, message: str = "Resource conflict.", details: dict = None):
        super().__init__(message, details)


class MethodNotAllowedError(ApiError):
    status_code = 405
    error_code = "method_not_allowed"

    def __init__(self, message: str = "HTTP method not allowed on this route.", details: dict = None):
        super().__init__(message, details)


class RouteNotFoundError(ApiError):
    status_code = 404
    error_code = "route_not_found"

    def __init__(self, message: str = "No route matches this request.", details: dict = None):
        super().__init__(message, details)
