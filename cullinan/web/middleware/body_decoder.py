# -*- coding: utf-8 -*-
"""Cullinan Body Decoder Middleware

Request body decoding middleware, automatically decodes the request body before it enters the Handler.

Author: Cullinan
"""

import logging
from typing import Any

from .base import Middleware

logger = logging.getLogger(__name__)


class BodyDecoderMiddleware(Middleware):
    """Request body decoding middleware

    Automatically decodes the request body and stores it in the request object
    before it enters the Handler.

    Features:
    - Decode once, available globally
    - Supports multiple Content-Types (via CodecRegistry)
    - Configurable enable/disable
    - Configurable error handling strategy on decode failure

    Example:
        from cullinan.web.middleware import get_middleware_registry
        from cullinan.web.middleware.body_decoder import BodyDecoderMiddleware

        # Register middleware
        registry = get_middleware_registry()
        registry.register(BodyDecoderMiddleware())

        # Get decoded request body in controller
        decoded_body = get_decoded_body(self.request)
    """

    def __init__(
        self,
        enabled: bool = True,
        fail_silently: bool = True,
        max_body_size: int = 10 * 1024 * 1024,  # 10MB
    ):
        """Initialize middleware

        Args:
            enabled: Whether to enable decoding
            fail_silently: Whether to silently handle decode failures (False returns 400 error)
            max_body_size: Maximum request body size (bytes)
        """
        super().__init__()
        self.enabled = enabled
        self.fail_silently = fail_silently
        self.max_body_size = max_body_size

    def process_request(self, handler: Any) -> Any:
        """Request preprocessing: decode request body

        Args:
            handler: Transport layer handler-like object

        Returns:
            handler or None (short-circuits request processing)
        """
        if not self.enabled:
            return handler

        request = handler.request

        # Check request body size
        body = request.body
        if body and len(body) > self.max_body_size:
            logger.warning(
                f"Request body too large: {len(body)} bytes > {self.max_body_size} bytes"
            )
            if not self.fail_silently:
                handler.set_status(413)
                handler.write({"error": "Request body too large"})
                handler.finish()
                return None
            # Silent mode: set empty dict
            setattr(request, '_decoded_body', {})
            return handler

        # Get Content-Type
        content_type = request.headers.get('Content-Type', '')

        # Detect character encoding
        charset = self._detect_charset(content_type)

        # Decode
        try:
            from cullinan.codec import get_codec_registry

            registry = get_codec_registry()
            decoded = registry.decode_body(body or b'', content_type, charset)

            # Store in request object
            setattr(request, '_decoded_body', decoded)

            logger.debug(
                f"Decoded request body: content_type={content_type}, "
                f"charset={charset}, keys={list(decoded.keys())}"
            )

        except Exception as e:
            logger.warning(f"Failed to decode request body: {e}")
            if not self.fail_silently:
                handler.set_status(400)
                handler.write({"error": f"Request body decode failed: {e}"})
                handler.finish()
                return None
            setattr(request, '_decoded_body', {})

        return handler

    def _detect_charset(self, content_type: str) -> str:
        """Detect character encoding from Content-Type

        Args:
            content_type: Content-Type header

        Returns:
            Character encoding (defaults to utf-8)
        """
        if 'charset=' in content_type:
            try:
                parts = content_type.split('charset=')
                if len(parts) > 1:
                    charset = parts[1].strip().split(';')[0].strip()
                    return charset.strip('"\'')
            except Exception:
                pass
        return 'utf-8'

    def on_startup(self):
        """Middleware startup initialization"""
        logger.debug(
            f"BodyDecoderMiddleware initialized: enabled={self.enabled}, "
            f"fail_silently={self.fail_silently}, max_body_size={self.max_body_size}"
        )


def get_decoded_body(request: Any) -> dict:
    """Get the decoded request body

    Args:
        request: Tornado request object (or handler.request)

    Returns:
        Decoded dict (returns empty dict if not decoded or decode failed)

    Example:
        class MyController:
            @post_api(url="/users")
            async def create_user(self):
                body = get_decoded_body(self.request)
                name = body.get('name')
    """
    return getattr(request, '_decoded_body', {})


def set_decoded_body(request: Any, data: dict) -> None:
    """Manually set the decoded request body (for testing)

    Args:
        request: Tornado request object
        data: Data to set
    """
    setattr(request, '_decoded_body', data)
