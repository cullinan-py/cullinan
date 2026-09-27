# -*- coding: utf-8 -*-
"""Cullinan Codec Module

Provides request body and response body encoding/decoding functionality.

Supported formats:
- JSON (application/json)
- Form (application/x-www-form-urlencoded)
- Extensible custom formats

Author: plumeink
"""

from .base import BodyCodec, ResponseCodec
from .errors import CodecError, DecodeError, EncodeError
from .json_codec import JsonBodyCodec, JsonResponseCodec
from .form_codec import FormBodyCodec
from .registry import (
    CodecRegistry,
    get_codec_registry,
    reset_codec_registry,
)

__all__ = [
    # Abstract base classes
    'BodyCodec',
    'ResponseCodec',

    # Error types
    'CodecError',
    'DecodeError',
    'EncodeError',

    # Built-in Codecs
    'JsonBodyCodec',
    'JsonResponseCodec',
    'FormBodyCodec',

    # Registry
    'CodecRegistry',
    'get_codec_registry',
    'reset_codec_registry',
]

