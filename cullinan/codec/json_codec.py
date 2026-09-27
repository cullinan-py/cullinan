# -*- coding: utf-8 -*-
"""Cullinan JSON Codec

JSON request body decoder and response encoder implementation.

Author: plumeink
"""

import json
from typing import Any, Dict

from .base import BodyCodec, ResponseCodec
from .errors import DecodeError, EncodeError


class JsonBodyCodec(BodyCodec):
    """JSON request body decoder

    Supported Content-Types:
    - application/json
    - text/json
    - application/json; charset=utf-8
    """

    content_types = ['application/json', 'text/json']
    priority = 10  # High priority

    def decode(self, body: bytes, charset: str = 'utf-8') -> Dict[str, Any]:
        """Decode a JSON request body

        Args:
            body: Raw request body bytes
            charset: Character encoding

        Returns:
            Decoded dictionary (empty body returns empty dict)

        Raises:
            DecodeError: JSON parsing failed
        """
        if not body:
            return {}

        try:
            decoded = body.decode(charset)
            result = json.loads(decoded)

            # Ensure we return a dict
            if isinstance(result, dict):
                return result
            # Wrap non-dict values (e.g., JSON arrays or scalars)
            return {'_value': result}

        except UnicodeDecodeError as e:
            raise DecodeError(
                f"Failed to decode body with charset '{charset}': {e}",
                content_type='application/json',
                body_preview=body
            )
        except json.JSONDecodeError as e:
            raise DecodeError(
                f"Invalid JSON: {e}",
                content_type='application/json',
                body_preview=body
            )

    def encode(self, data: Dict[str, Any], charset: str = 'utf-8') -> bytes:
        """Encode to JSON

        Args:
            data: Dictionary to encode
            charset: Character encoding

        Returns:
            JSON bytes
        """
        try:
            return json.dumps(data, ensure_ascii=False).encode(charset)
        except (TypeError, ValueError) as e:
            raise EncodeError(
                f"Failed to encode as JSON: {e}",
                data_type=type(data)
            )


class JsonResponseCodec(ResponseCodec):
    """JSON response encoder

    Encodes response data to JSON format.
    """

    content_type = 'application/json'
    accept_types = ['application/json', 'text/json', '*/*']
    priority = 10  # High priority

    def encode(self, data: Any, charset: str = 'utf-8') -> bytes:
        """Encode response data as JSON

        Args:
            data: Response data (can be any JSON-serializable type)
            charset: Character encoding

        Returns:
            JSON bytes

        Raises:
            EncodeError: Serialization failed
        """
        try:
            # Use default=str to handle non-serializable types
            return json.dumps(
                data,
                ensure_ascii=False,
                default=str
            ).encode(charset)
        except Exception as e:
            raise EncodeError(
                f"Failed to encode response as JSON: {e}",
                data_type=type(data)
            )

