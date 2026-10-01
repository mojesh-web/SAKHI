class SakhiBaseException(Exception):
    """Base exception for Sakhi app."""

    status_code = 500


class GroqAPIError(SakhiBaseException):
    """Raised when Groq API calls fail."""

    def __init__(self, message, status_code=500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class InvalidAudioError(SakhiBaseException):
    """Raised when uploaded audio is invalid."""

    status_code = 400


class ConfigurationError(SakhiBaseException):
    """Raised when app configuration is invalid."""

    status_code = 500
