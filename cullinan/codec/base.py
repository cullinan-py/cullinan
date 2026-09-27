# -*- coding: utf-8 -*-
"""Cullinan Codec Base Classes

Defines the BodyCodec and ResponseCodec abstract base classes.

Author: plumeink
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BodyCodec(ABC):
    """Abstract base class for request body codecs

    Responsibilities:
    - decode: bytes → dict (request decoding)
    - encode: dict → bytes (optional, for certain scenarios)

    Characteristics:
    - Pure encoding/decoding, no business logic
    - Can be invoked uniformly in Middleware

    Example:
        class JsonBodyCodec(BodyCodec):
            content_types = ['application/json']

            def decode(self, body, charset='utf-8'):
                return json.loads(body.decode(charset))
    """

    # Supported Content-Type list (subclasses must override)
    content_types: List[str] = []

    # Priority (smaller number = higher priority)
    priority: int = 100

    @abstractmethod
    def decode(self, body: bytes, charset: str = 'utf-8') -> Dict[str, Any]:
        """Decode the request body

        Args:
            body: Raw request body bytes
            charset: Character encoding

        Returns:
            Decoded dictionary

        Raises:
            DecodeError: Decoding failed
        """
        pass

    def encode(self, data: Dict[str, Any], charset: str = 'utf-8') -> bytes:
        """Encode data (optional implementation)

        Args:
            data: Dictionary to encode
            charset: Character encoding

        Returns:
            Encoded bytes

        Raises:
            EncodeError: Encoding failed
        """
        raise NotImplementedError("This codec does not support encoding")

    @classmethod
    def supports(cls, content_type: str) -> bool:
        """Check if this codec supports the given Content-Type

        Args:
            content_type: HTTP Content-Type header

        Returns:
            True if supported, False otherwise
        """
        if not content_type:
            return False
        ct_lower = content_type.lower()
        for ct in cls.content_types:
            if ct in ct_lower:
                return True
        return False


class ResponseCodec(ABC):
    """Abstract base class for response body codecs

    Responsibilities:
    - encode: Any → bytes (response encoding)
    - Set the correct Content-Type

    Use cases:
    - Unified response format (JSON/XML/MessagePack)
    - Content negotiation (Accept header)

    Example:
        class JsonResponseCodec(ResponseCodec):
            content_type = 'application/json'
            accept_types = ['application/json', '*/*']

            def encode(self, data, charset='utf-8'):
                return json.dumps(data).encode(charset)
    """

    # Output Content-Type
    content_type: str = 'application/octet-stream'

    # Supported Accept types
    accept_types: List[str] = []

    # Priority
    priority: int = 100

    @abstractmethod
    def encode(self, data: Any, charset: str = 'utf-8') -> bytes:
        """Encode response data

        Args:
            data: Response data (can be any type)
            charset: Character encoding

        Returns:
            Encoded bytes

        Raises:
            EncodeError: Encoding failed
        """
        pass

    def get_content_type(self, charset: str = 'utf-8') -> str:
        """Get the full Content-Type header

        Args:
            charset: Character encoding

        Returns:
            Full Content-Type string
        """
        if 'charset' not in self.content_type.lower():
            return f"{self.content_type}; charset={charset}"
        return self.content_type

    @classmethod
    def supports_accept(cls, accept: str) -> bool:
        """Check if this codec supports the given Accept type

        Args:
            accept: HTTP Accept header

        Returns:
            True if supported, False otherwise
        """
        if not accept or accept == '*/*':
            return True
        accept_lower = accept.lower()
        for at in cls.accept_types:
            if at in accept_lower:
                return True
        return False

