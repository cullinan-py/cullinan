# -*- coding: utf-8 -*-
"""Cullinan Form Codec

Form-encoded request body decoder implementation.

Author: plumeink
"""

from urllib.parse import parse_qs, urlencode
from typing import Any, Dict

from .base import BodyCodec
from .errors import DecodeError, EncodeError


class FormBodyCodec(BodyCodec):
    """Form body decoder

    Supported Content-Types:
    - application/x-www-form-urlencoded
    """

    content_types = ['application/x-www-form-urlencoded']
    priority = 20

    def decode(self, body: bytes, charset: str = 'utf-8') -> Dict[str, Any]:
        """Decode a Form request body

        Args:
            body: Raw request body bytes
            charset: Character encoding

        Returns:
            Decoded dictionary (flatten single-value fields to scalar)

        Raises:
            DecodeError: Parsing failed
        """
        if not body:
            return {}

        try:
            decoded = body.decode(charset)
            parsed = parse_qs(decoded, keep_blank_values=True)

            # Flatten single-value fields to scalar, keep multi-value as list
            result = {}
            for key, values in parsed.items():
                if len(values) == 1:
                    result[key] = values[0]
                else:
                    result[key] = values

            return result

        except UnicodeDecodeError as e:
            raise DecodeError(
                f"Failed to decode form body with charset '{charset}': {e}",
                content_type='application/x-www-form-urlencoded',
                body_preview=body
            )
        except Exception as e:
            raise DecodeError(
                f"Failed to parse form body: {e}",
                content_type='application/x-www-form-urlencoded',
                body_preview=body
            )

    def encode(self, data: Dict[str, Any], charset: str = 'utf-8') -> bytes:
        """Encode to Form format

        Args:
            data: Dictionary to encode
            charset: Character encoding

        Returns:
            URL-encoded bytes

        Raises:
            EncodeError: Encoding failed
        """
        try:
            # Handle list values
            encoded_data = {}
            for key, value in data.items():
                if isinstance(value, list):
                    encoded_data[key] = value
                else:
                    encoded_data[key] = str(value)

            return urlencode(encoded_data, doseq=True).encode(charset)

        except Exception as e:
            raise EncodeError(
                f"Failed to encode as form data: {e}",
                data_type=type(data)
            )

