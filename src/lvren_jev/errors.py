from __future__ import annotations


class TypesafeJevError(Exception):
    """Base class for errors raised by the generic decision library."""


class DefinitionError(TypesafeJevError, ValueError):
    """The decision definition is missing, malformed, or unsupported."""


class JevRuntimeError(TypesafeJevError):
    """A Jev invocation failed after runtime policies were applied."""

    def __init__(self, code: str, message: str, *, cause: Exception | None = None):
        self.code = code
        self.cause = cause
        super().__init__(message)
