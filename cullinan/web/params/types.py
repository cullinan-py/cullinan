# -*- coding: utf-8 -*-
"""Cullinan Parameter Types

Defines various parameter source types: Path, Query, Body, Header, File.

Author: Cullinan
"""

from typing import Any, List, Optional, Type

from .base import Param, UNSET


class Path(Param):
    """URL path parameter

    Parameter extracted from the URL path, such as id in /users/{id}.
    Path parameters are always required.

    Example:
        @get_api(url="/users/{id}")
        async def get_user(self, id: int = Path()):
            # id has already been converted to int type
            pass

        @get_api(url="/users/{id}/posts/{post_id}")
        async def get_post(self, id: int = Path(), post_id: int = Path()):
            pass
    """
    _source = 'path'

    def __init__(
        self,
        type_: Type = str,
        *,
        name: str = None,
        description: str = '',
        alias: str = None,
        # Numeric constraints
        ge: Any = None,
        le: Any = None,
        gt: Any = None,
        lt: Any = None,
        # Length constraints
        min_length: int = None,
        max_length: int = None,
        # Regex constraints
        regex: str = None,
    ):
        """Initialize path parameter

        Note:
            Path parameters are always required and do not support default values.
        """
        super().__init__(
            type_=type_,
            name=name,
            required=True,  # Path parameters are always required
            default=UNSET,  # Default values not supported
            description=description,
            alias=alias,
            ge=ge,
            le=le,
            gt=gt,
            lt=lt,
            min_length=min_length,
            max_length=max_length,
            regex=regex,
        )


class Query(Param):
    """Query parameter

    Parameter extracted from the URL query string, such as ?page=1&size=10.

    Example:
        @get_api(url="/users")
        async def list_users(
            self,
            page: int = Query(default=1, ge=1),
            size: int = Query(default=10, ge=1, le=100),
            q: str = Query(required=False),
        ):
            pass

        # Plain type annotation is automatically treated as Query (v0.90a5+)
        @get_api(url="/items")
        async def list_items(self, page: int = 1, size: int = 10):
            pass
    """
    _source = 'query'

    # Inherits Param's __init__, no need to override

class Body(Param):
    """Request body parameter

    Parameter extracted from the request body. Transport format (JSON/Form) is handled by the Codec layer.

    Example:
        # Single field (new unified syntax)
        @post_api(url="/users")
        async def create_user(
            self,
            name: str = Body(required=True),
            age: int = Body(default=0, ge=0),
        ):
            pass

        # Use as_required() shortcut
        @post_api(url="/users")
        async def create_user(
            self,
            name: str = Body.as_required(min_length=1),
        ):
            pass

        # Use with DynamicBody for the entire request body
        @post_api(url="/users")
        async def create_user(self, body: DynamicBody):
            print(body.name, body.age)
    """
    _source = 'body'

    # Inherits Param's __init__, no need to override


class RawBody(Param):
    """Raw request body (unparsed bytes)

    Gets the unparsed raw request body bytes, suitable for:
    - Signature verification (e.g., GitHub Webhook)
    - Custom parsing formats
    - Binary data processing

    Example:
        @post_api(url="/webhook")
        async def handle_webhook(
            self,
            sign: str = Header(alias="X-Hub-Signature-256"),
            event: str = Header(alias="X-GitHub-Event"),
            raw_body: bytes = RawBody(),  # Recommended syntax
        ):
            # raw_body is of bytes type
            import hmac
            expected = hmac.new(secret, raw_body, 'sha256').hexdigest()
            if sign != f'sha256={expected}':
                raise ValueError('Invalid signature')

            # Manual parsing
            import json
            data = json.loads(raw_body)
    """
    _source = 'raw_body'

    def __init__(
        self,
        *,
        name: str = None,
        required: bool = False,
        description: str = '',
    ):
        """Initialize raw request body parameter

        Args:
            name: Parameter name
            required: Whether required (default False)
            description: Parameter description
        """
        super().__init__(
            type_=bytes,
            name=name,
            required=required,
            default=b'',
            description=description,
        )


class Header(Param):
    """Request header parameter

    Parameter extracted from HTTP request headers.
    Typically uses alias to specify the actual header name.
    HTTP header matching is case-insensitive (per RFC 7230).

    Example:
        @get_api(url="/users")
        async def list_users(
            self,
            auth: str = Header(alias='Authorization', required=True),
            request_id: str = Header(alias='X-Request-ID', required=False),
        ):
            pass

        # GitHub Webhook signature verification
        @post_api(url="/webhook")
        async def handle_webhook(
            self,
            sign: str = Header(alias="X-Hub-Signature-256"),
            event: str = Header(alias="X-GitHub-Event"),
            raw_body: RawBody,
        ):
            pass
    """
    _source = 'header'

    def __init__(
        self,
        type_: Type = str,
        *,
        name: str = None,
        required: bool = True,
        default: Any = UNSET,
        description: str = '',
        alias: str = None,
        # Length constraints
        min_length: int = None,
        max_length: int = None,
        # Regex constraints
        regex: str = None,
    ):
        """Initialize request header parameter

        Note:
            Request header parameters typically use alias to specify the actual header name,
            such as Authorization, Content-Type, X-Request-ID, etc.
        """
        super().__init__(
            type_=type_,
            name=name,
            required=required,
            default=default,
            description=description,
            alias=alias,
            min_length=min_length,
            max_length=max_length,
            regex=regex,
        )


class File(Param):
    """File parameter

    File extracted from a multipart/form-data request.

    Attributes:
        max_size: Maximum file size (bytes)
        allowed_types: List of allowed MIME types
        multiple: Whether multiple file upload is supported
        max_count: Maximum number of files when uploading multiple files

    Example:
        # Single file upload (new unified syntax)
        @post_api(url="/upload")
        async def upload(
            self,
            avatar: File = File(max_size=5*1024*1024),  # 5MB
        ):
            print(avatar.filename)
            print(avatar.size)
            avatar.save('/uploads/')

        # Use as_required() shortcut
        @post_api(url="/upload-required")
        async def upload_required(
            self,
            avatar: File = File.as_required(max_size=5*1024*1024),
        ):
            pass

        # With type validation
        @post_api(url="/upload-image")
        async def upload_image(
            self,
            image: File = File(allowed_types=['image/png', 'image/jpeg', 'image/*']),
        ):
            pass

        # Multiple file upload
        @post_api(url="/upload-multiple")
        async def upload_multiple(
            self,
            files: File = File(multiple=True, max_count=10),
        ):
            for f in files:
                print(f.filename)
    """
    _source = 'file'

    # Extend __slots__
    __slots__ = ('max_size', 'allowed_types', 'multiple', 'max_count', 'min_size')

    def __init__(
        self,
        *,
        name: str = None,
        required: bool = True,
        description: str = '',
        alias: str = None,
        max_size: Optional[int] = None,
        min_size: Optional[int] = None,
        allowed_types: Optional[List[str]] = None,
        multiple: bool = False,
        max_count: Optional[int] = None,
    ):
        """Initialize file parameter

        Args:
            name: Parameter name
            required: Whether required
            description: Parameter description
            alias: Alias (form field name)
            max_size: Maximum file size (bytes)
            min_size: Minimum file size (bytes)
            allowed_types: List of allowed MIME types, supports wildcards like 'image/*'
            multiple: Whether multiple file upload is supported
            max_count: Maximum number of files when uploading multiple files
        """
        super().__init__(
            type_=bytes,  # File content is bytes
            name=name,
            required=required,
            default=UNSET,
            description=description,
            alias=alias,
        )
        self.max_size = max_size
        self.min_size = min_size
        self.allowed_types = allowed_types or []
        self.multiple = multiple
        self.max_count = max_count

    def validate_file(self, file_info) -> None:
        """Validate file

        Args:
            file_info: FileInfo instance

        Raises:
            ValueError: Validation failed
        """
        # Validate file size
        if self.max_size is not None and file_info.size > self.max_size:
            raise ValueError(
                f"File '{file_info.filename}' size ({file_info.size} bytes) "
                f"exceeds maximum allowed size ({self.max_size} bytes)"
            )

        if self.min_size is not None and file_info.size < self.min_size:
            raise ValueError(
                f"File '{file_info.filename}' size ({file_info.size} bytes) "
                f"is below minimum required size ({self.min_size} bytes)"
            )

        # Validate MIME type
        if self.allowed_types:
            if not self._match_content_type(file_info.content_type):
                raise ValueError(
                    f"File '{file_info.filename}' type '{file_info.content_type}' "
                    f"is not allowed. Allowed types: {self.allowed_types}"
                )

    def validate_file_list(self, file_list) -> None:
        """Validate file list

        Args:
            file_list: FileList instance

        Raises:
            ValueError: Validation failed
        """
        # Validate file count
        if self.max_count is not None and len(file_list) > self.max_count:
            raise ValueError(
                f"Number of files ({len(file_list)}) exceeds maximum allowed ({self.max_count})"
            )

        # Validate each file
        for file_info in file_list:
            self.validate_file(file_info)

    def _match_content_type(self, content_type: str) -> bool:
        """Check if MIME type matches allowed list

        Args:
            content_type: File MIME type

        Returns:
            Whether it matches
        """
        for pattern in self.allowed_types:
            if pattern == '*/*' or pattern == '*':
                return True
            if pattern.endswith('/*'):
                # Wildcard match
                prefix = pattern[:-1]  # 'image/'
                if content_type.startswith(prefix):
                    return True
            elif content_type == pattern:
                return True
        return False

    def __repr__(self) -> str:
        parts = ["File("]
        if self.name:
            parts.append(f"name={self.name!r}, ")
        if not self.required:
            parts.append("required=False, ")
        if self.max_size:
            parts.append(f"max_size={self.max_size}, ")
        if self.min_size:
            parts.append(f"min_size={self.min_size}, ")
        if self.allowed_types:
            parts.append(f"allowed_types={self.allowed_types!r}, ")
        if self.multiple:
            parts.append("multiple=True, ")
        if self.max_count:
            parts.append(f"max_count={self.max_count}, ")
        result = "".join(parts)
        if result.endswith(", "):
            result = result[:-2]
        return result + ")"

    @classmethod
    def as_required(
        cls,
        *,
        name: str = None,
        description: str = '',
        alias: str = None,
        max_size: Optional[int] = None,
        min_size: Optional[int] = None,
        allowed_types: Optional[List[str]] = None,
        multiple: bool = False,
        max_count: Optional[int] = None,
    ) -> 'File':
        """Shortcut method to create a required file parameter

        Example:
            # The following two forms are equivalent
            avatar: File = File.as_required(max_size=5*1024*1024)
            avatar: File = File(required=True, max_size=5*1024*1024)

        Returns:
            File instance with required=True
        """
        return cls(
            name=name,
            required=True,
            description=description,
            alias=alias,
            max_size=max_size,
            min_size=min_size,
            allowed_types=allowed_types,
            multiple=multiple,
            max_count=max_count,
        )

