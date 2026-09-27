# -*- coding: utf-8 -*-
"""Cullinan Codec Registry

Codec registry that manages all BodyCodec and ResponseCodec instances.

Author: plumeink
"""

from typing import Any, Dict, List, Optional, Tuple, Type

from .base import BodyCodec, ResponseCodec


class CodecRegistry:
    """Codec registry

    Manages registration and selection of all BodyCodec and ResponseCodec instances.

    Example:
        registry = get_codec_registry()

        # Decode request body
        data = registry.decode_body(body, 'application/json')

        # Encode response
        encoded, content_type = registry.encode_response(data, 'application/json')

        # Register custom Codec
        registry.register_body_codec(XmlBodyCodec)
    """

    def __init__(self):
        self._body_codecs: List[Type[BodyCodec]] = []
        self._response_codecs: List[Type[ResponseCodec]] = []

    def register_body_codec(self, codec_class: Type[BodyCodec]) -> None:
        """Register a body codec

        Args:
            codec_class: BodyCodec subclass
        """
        if codec_class not in self._body_codecs:
            self._body_codecs.append(codec_class)
            # Sort by priority (smaller number = higher priority)
            self._body_codecs.sort(key=lambda c: c.priority)

    def register_response_codec(self, codec_class: Type[ResponseCodec]) -> None:
        """Register a response codec

        Args:
            codec_class: ResponseCodec subclass
        """
        if codec_class not in self._response_codecs:
            self._response_codecs.append(codec_class)
            self._response_codecs.sort(key=lambda c: c.priority)

    def unregister_body_codec(self, codec_class: Type[BodyCodec]) -> None:
        """Unregister a body codec"""
        if codec_class in self._body_codecs:
            self._body_codecs.remove(codec_class)

    def unregister_response_codec(self, codec_class: Type[ResponseCodec]) -> None:
        """Unregister a response codec"""
        if codec_class in self._response_codecs:
            self._response_codecs.remove(codec_class)

    def get_body_codec(self, content_type: str) -> Optional[BodyCodec]:
        """Get a body codec instance by Content-Type

        Args:
            content_type: HTTP Content-Type header

        Returns:
            Codec instance, or None if no match
        """
        for codec_class in self._body_codecs:
            if codec_class.supports(content_type):
                return codec_class()
        return None

    def get_response_codec(self, accept: str = '*/*') -> Optional[ResponseCodec]:
        """Get a response codec instance by Accept type

        Args:
            accept: HTTP Accept header

        Returns:
            Codec instance, or None if no match
        """
        for codec_class in self._response_codecs:
            if codec_class.supports_accept(accept):
                return codec_class()
        return None

    def decode_body(
        self,
        body: bytes,
        content_type: str,
        charset: str = 'utf-8'
    ) -> Dict[str, Any]:
        """Decode the request body

        Args:
            body: Raw request body bytes
            content_type: Content-Type header
            charset: Character encoding

        Returns:
            Decoded dictionary

        Raises:
            DecodeError: Decoding failed
        """
        codec = self.get_body_codec(content_type)
        if codec:
            return codec.decode(body, charset)

        # Fall back to JSON
        from .json_codec import JsonBodyCodec
        return JsonBodyCodec().decode(body, charset)

    def encode_response(
        self,
        data: Any,
        accept: str = '*/*',
        charset: str = 'utf-8'
    ) -> Tuple[bytes, str]:
        """Encode the response

        Args:
            data: Response data
            accept: Accept header
            charset: Character encoding

        Returns:
            (encoded bytes, Content-Type)

        Raises:
            EncodeError: Encoding failed
        """
        codec = self.get_response_codec(accept)
        if codec:
            return codec.encode(data, charset), codec.get_content_type(charset)

        # Fall back to JSON
        from .json_codec import JsonResponseCodec
        default_codec = JsonResponseCodec()
        return default_codec.encode(data, charset), default_codec.get_content_type(charset)

    def list_body_codecs(self) -> List[Type[BodyCodec]]:
        """List all registered body codecs"""
        return list(self._body_codecs)

    def list_response_codecs(self) -> List[Type[ResponseCodec]]:
        """List all registered response codecs"""
        return list(self._response_codecs)


# Global registry instance
_codec_registry: Optional[CodecRegistry] = None


def get_codec_registry() -> CodecRegistry:
    """Get the global Codec registry

    Returns:
        CodecRegistry singleton
    """
    global _codec_registry
    if _codec_registry is None:
        _codec_registry = CodecRegistry()
        # Register default codecs
        from .json_codec import JsonBodyCodec, JsonResponseCodec
        from .form_codec import FormBodyCodec
        _codec_registry.register_body_codec(JsonBodyCodec)
        _codec_registry.register_body_codec(FormBodyCodec)
        _codec_registry.register_response_codec(JsonResponseCodec)
    return _codec_registry


def reset_codec_registry() -> None:
    """Reset the global registry (for testing)"""
    global _codec_registry
    _codec_registry = None

