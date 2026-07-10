# -*- coding: utf-8 -*-
"""Cullinan Parameter Resolver

Parameter resolution orchestrator, coordinates all layers to complete parameter resolution.

Author: Cullinan
"""

import inspect
from typing import Any, Callable, Dict, Optional, Union, get_args, get_origin, get_type_hints

from .base import Param, UNSET
from .types import File, RawBody
from .converter import TypeConverter, ConversionError
from .auto import Auto, AutoType
from .dynamic import DynamicBody
from .validator import ParamValidator, ValidationError
from .model import ModelError
from .file_info import FileInfo, FileList
from .model_handlers import get_model_handler_registry


class ResolveError(Exception):
    """Parameter resolution error

    Attributes:
        message: Error message
        errors: List of error details
    """

    def __init__(self, message: str, errors: list = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or []

    def to_dict(self) -> dict:
        """Convert to dict format"""
        return {
            'message': self.message,
            'errors': self.errors,
        }


class ParamResolver:
    """Parameter resolution orchestrator

    Coordinates transport layer, conversion layer, and data layer to complete parameter resolution.

    Features:
    - Derives parameter config from function signature
    - Supports traditional decorator config
    - Automatic type conversion
    - Parameter validation
    - dataclass / DynamicBody support

    Example:
        @post_api(url="/users")
        async def create_user(
            self,
            name: Body(str, required=True),
            age: Body(int, default=0, ge=0),
        ):
            pass

        # ParamResolver will automatically resolve name and age parameters
    """

    # Signature cache
    _signature_cache: Dict[Callable, inspect.Signature] = {}

    @classmethod
    def _get_header_value(cls, headers: Dict[str, str], key: str) -> Optional[str]:
        """Get header value with case-insensitive matching

        HTTP headers are case-insensitive per RFC 7230.

        Args:
            headers: Header dictionary
            key: Header name to look up

        Returns:
            Header value or None
        """
        if not headers or not key:
            return None

        # Try exact match first
        if key in headers:
            return headers[key]

        # Try case-insensitive match
        key_lower = key.lower()
        for header_key, header_value in headers.items():
            if header_key.lower() == key_lower:
                return header_value

        return None

    @classmethod
    def get_signature(cls, func: Callable) -> inspect.Signature:
        """Get function signature (with caching)

        Args:
            func: Function

        Returns:
            Function signature
        """
        if func not in cls._signature_cache:
            cls._signature_cache[func] = inspect.signature(func)
        return cls._signature_cache[func]

    @classmethod
    def analyze_params(cls, func: Callable) -> Dict[str, dict]:
        """Analyze function parameter config

        Args:
            func: Controller method

        Returns:
            Parameter config dict {param_name: {source, type, param_spec, ...}}
        """
        sig = cls.get_signature(func)
        type_hints = {}
        try:
            type_hints = get_type_hints(func)
        except Exception:
            pass

        params_config = {}

        for name, param in sig.parameters.items():
            # Skip self parameter
            if name == 'self':
                continue

            config = {
                'name': name,
                'source': 'unknown',
                'type': str,
                'required': True,
                'default': UNSET,
                'param_spec': None,
            }

            # Check type annotation
            annotation = type_hints.get(name, param.annotation)

            # Unwrap Optional[X] → X when get_type_hints wraps ``T = None``
            # as Optional[T] (behaviour varies across Python versions).
            if annotation is not None and annotation is not inspect.Parameter.empty:
                origin = get_origin(annotation)
                if origin is Union:
                    args = get_args(annotation)
                    non_none = [a for a in args if a is not type(None)]
                    if len(non_none) == 1:
                        annotation = non_none[0]

            if annotation is inspect.Parameter.empty:
                annotation = None

            # First check if default value is a Param instance (supports simplified syntax)
            # e.g.: sign: str = Header(alias="X-Hub-Signature-256")
            if param.default is not inspect.Parameter.empty and isinstance(param.default, Param):
                param_spec = param.default
                config['source'] = param_spec.source
                # If Param did not specify a type, get it from the annotation
                if param_spec.type_ is str and annotation is not None and annotation is not str:
                    config['type'] = annotation
                else:
                    config['type'] = param_spec.type_
                config['required'] = param_spec.required
                config['default'] = param_spec.default
                config['param_spec'] = param_spec
                # Use parameter name as name (if not specified)
                if param_spec.name is None:
                    param_spec.name = name

            # Check if default value is a DynamicBody instance
            # e.g.: body: DynamicBody = DynamicBody()
            elif param.default is not inspect.Parameter.empty and isinstance(param.default, DynamicBody):
                config['source'] = 'body'
                config['type'] = DynamicBody
                config['required'] = False
                config['default'] = param.default

            # Check if it is a Param instance (type annotation style)
            elif isinstance(annotation, Param):
                param_spec = annotation
                config['source'] = param_spec.source
                config['type'] = param_spec.type_
                config['required'] = param_spec.required
                config['default'] = param_spec.default
                config['param_spec'] = param_spec
                # Use parameter name as name (if not specified)
                if param_spec.name is None:
                    param_spec.name = name

            # Check if it is DynamicBody (or its subclass)
            elif (annotation is DynamicBody
                  or (isinstance(annotation, type)
                      and getattr(annotation, '__name__', '') == 'DynamicBody'
                      and getattr(annotation, '__module__', '') == DynamicBody.__module__)):
                config['source'] = 'body'
                config['type'] = DynamicBody
                config['required'] = False

            # Check if it is RawBody (the class itself, no parentheses needed)
            elif (annotation is RawBody
                  or (isinstance(annotation, type)
                      and getattr(annotation, '__name__', '') == 'RawBody'
                      and getattr(annotation, '__module__', '') == RawBody.__module__)):
                config['source'] = 'raw_body'
                config['type'] = bytes
                config['required'] = False

            # Check if it is a handlable model type (via registry)
            elif get_model_handler_registry().can_handle(annotation):
                handler = get_model_handler_registry().get_handler(annotation)
                config['source'] = handler.get_source()
                config['type'] = annotation
                config['required'] = handler.is_required_by_default()
                config['model_handler'] = handler

            # Check if it is AutoType
            elif (annotation is AutoType
                  or (isinstance(annotation, type)
                      and getattr(annotation, '__name__', '') == 'AutoType'
                      and getattr(annotation, '__module__', '') == AutoType.__module__)):
                config['source'] = 'auto'
                config['type'] = AutoType

            # Plain type annotation (defaults to Query parameter)
            elif annotation in (str, int, float, bool):
                config['source'] = 'query'
                config['type'] = annotation

            # Other type annotations
            elif annotation is not None:
                config['type'] = annotation

            # Check default value (plain default value that is not a Param instance)
            if param.default is not inspect.Parameter.empty and not isinstance(param.default, Param):
                config['default'] = param.default
                config['required'] = False

            params_config[name] = config

        return params_config

    @classmethod
    def resolve(
        cls,
        func: Callable,
        request: Any,
        url_params: Dict[str, Any] = None,
        query_params: Dict[str, Any] = None,
        body_data: Dict[str, Any] = None,
        headers: Dict[str, str] = None,
        files: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Resolve request parameters

        Args:
            func: Controller method
            request: Tornado request object
            url_params: URL path parameters
            query_params: Query parameters
            body_data: Request body data (decoded)
            headers: Request headers
            files: Uploaded files

        Returns:
            Resolved parameter dict {param_name: value}

        Raises:
            ResolveError: Resolution failed
        """
        url_params = url_params or {}
        query_params = query_params or {}
        body_data = body_data or {}
        headers = headers or {}
        files = files or {}

        # Analyze parameter config
        params_config = cls.analyze_params(func)

        result = {}
        errors = []

        for name, config in params_config.items():
            try:
                value = cls._resolve_param(
                    name, config,
                    url_params, query_params, body_data, headers, files, request
                )
                result[name] = value
            except (ConversionError, ValidationError, ModelError) as e:
                errors.append({
                    'param': name,
                    'error': str(e),
                    'type': type(e).__name__,
                })

        if errors:
            raise ResolveError(
                f"Failed to resolve {len(errors)} parameter(s)",
                errors=errors
            )

        return result

    @classmethod
    def _resolve_param(
        cls,
        name: str,
        config: dict,
        url_params: Dict[str, Any],
        query_params: Dict[str, Any],
        body_data: Dict[str, Any],
        headers: Dict[str, str],
        files: Dict[str, Any],
        request: Any = None,
    ) -> Any:
        """Resolve a single parameter

        Args:
            name: Parameter name
            config: Parameter config
            Various source data...
            request: Original request object (used for RawBody)

        Returns:
            Resolved value
        """
        source = config['source']
        target_type = config['type']
        required = config['required']
        default = config['default']
        param_spec = config.get('param_spec')

        # Get alias
        alias = name
        if param_spec and param_spec.alias:
            alias = param_spec.alias

        # Get raw value based on source
        raw_value = None

        if source == 'path':
            raw_value = url_params.get(alias) or url_params.get(name)
        elif source == 'query':
            raw_value = query_params.get(alias) or query_params.get(name)
        elif source == 'body':
            # Special handling for DynamicBody and model types
            if target_type is DynamicBody:
                return DynamicBody(body_data)
            elif config.get('model_handler'):
                # Use registered model handler
                return config['model_handler'].resolve(target_type, body_data)
            else:
                raw_value = body_data.get(alias) or body_data.get(name)
        elif source == 'header':
            # HTTP headers are case-insensitive, use lowercase matching
            raw_value = cls._get_header_value(headers, alias) or cls._get_header_value(headers, name)
        elif source == 'raw_body':
            # Return raw binary request body
            if request is not None and hasattr(request, 'body'):
                return request.body if request.body else b''
            return b''
        elif source == 'file':
            raw_value = files.get(alias) or files.get(name)
            # Handle file parameter
            if raw_value is not None:
                return cls._resolve_file_param(raw_value, param_spec, name)
        elif source == 'auto':
            # Auto type: search each source in order
            raw_value = (
                url_params.get(name) or
                query_params.get(name) or
                body_data.get(name)
            )
        else:
            # Unknown source: try getting from multiple places
            raw_value = (
                url_params.get(name) or
                query_params.get(name) or
                body_data.get(name)
            )

        # Handle None value
        if raw_value is None:
            if default is not UNSET:
                return default
            if required:
                raise ValidationError(
                    f"Parameter '{name}' is required",
                    param_name=name,
                    constraint='required'
                )
            return None

        # Type conversion
        if target_type is AutoType:
            converted = Auto.infer(raw_value)
        elif target_type is DynamicBody:
            if isinstance(raw_value, dict):
                converted = DynamicBody(raw_value)
            else:
                converted = raw_value
        elif config.get('model_handler'):
            # Use registered model handler
            if isinstance(raw_value, dict):
                converted = config['model_handler'].resolve(target_type, raw_value)
            else:
                converted = raw_value
        else:
            converted = TypeConverter.convert(raw_value, target_type)

        # Parameter validation
        if param_spec:
            ParamValidator.validate_param(param_spec, converted, name)

        return converted

    @classmethod
    def clear_cache(cls) -> None:
        """Clear signature cache"""
        cls._signature_cache.clear()

    @classmethod
    def _resolve_file_param(
        cls,
        raw_value: Any,
        param_spec: File,
        name: str,
    ) -> Any:
        """Resolve file parameter

        Args:
            raw_value: Raw file data (from transport adapter layer)
            param_spec: File parameter spec
            name: Parameter name

        Returns:
            FileInfo or FileList
        """
        # Handle list format (backend upload collections are usually lists)
        if isinstance(raw_value, list):
            file_list = []
            for item in raw_value:
                if isinstance(item, dict):
                    file_info = FileInfo.from_upload_payload(item)
                elif isinstance(item, FileInfo):
                    file_info = item
                else:
                    # Try treating as dict
                    file_info = FileInfo(
                        filename=getattr(item, 'filename', 'unknown'),
                        body=getattr(item, 'body', b''),
                        content_type=getattr(item, 'content_type', None),
                    )
                file_list.append(file_info)

            if param_spec and param_spec.multiple:
                # Multiple file mode
                result = FileList(file_list)
                if param_spec:
                    param_spec.validate_file_list(result)
                return result
            elif file_list:
                # Single file mode, take the first
                result = file_list[0]
                if param_spec:
                    param_spec.validate_file(result)
                return result
            else:
                return None

        # Handle single file
        if isinstance(raw_value, dict):
            file_info = FileInfo.from_upload_payload(raw_value)
        elif isinstance(raw_value, FileInfo):
            file_info = raw_value
        else:
            file_info = FileInfo(
                filename=getattr(raw_value, 'filename', 'unknown'),
                body=getattr(raw_value, 'body', b''),
                content_type=getattr(raw_value, 'content_type', None),
            )

        if param_spec:
            param_spec.validate_file(file_info)

        return file_info
