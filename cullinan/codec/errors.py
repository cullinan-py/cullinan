# -*- coding: utf-8 -*-
"""Cullinan Codec Errors

Defines exception classes for encoding/decoding operations.

Author: plumeink
"""

from typing import Optional


class CodecError(Exception):
    """Base codec error class"""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class DecodeError(CodecError):
    """Decoding error

    Raised when request body decoding fails.

    Attributes:
        message: Error message
        content_type: Content-Type of the request
        body_preview: Preview of the request body (first 100 bytes)
    """

    def __init__(
        self,
        message: str,
        content_type: str = None,
        body_preview: bytes = None,
        details: Optional[dict] = None
    ):
        super().__init__(message, details)
        self.content_type = content_type
        self.body_preview = body_preview[:100] if body_preview else None

    def __repr__(self) -> str:
        return f"DecodeError({self.message!r}, content_type={self.content_type!r})"


class EncodeError(CodecError):
    """Encoding error

    Raised when response body encoding fails.

    Attributes:
        message: Error message
        data_type: Data type that was being encoded
    """

    def __init__(
        self,
        message: str,
        data_type: type = None,
        details: Optional[dict] = None
    ):
        super().__init__(message, details)
        self.data_type = data_type

    def __repr__(self) -> str:
        return f"EncodeError({self.message!r}, data_type={self.data_type})"

