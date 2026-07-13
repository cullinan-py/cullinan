# -*- coding: utf-8 -*-
"""Cullinan Params Module

Provides parameter marker classes and type conversion utilities.

Supported parameter types:
- Path: URL path parameters
- Query: Query parameters
- Body: Request body parameters
- Header: Request header parameters
- File: File parameters
- RawBody: Raw binary request body

Type conversion:
- TypeConverter: Type converter
- Auto: Auto type inference
- DynamicBody: Dynamic request body

Validation:
- ParamValidator: Parameter validator
- field_validator: dataclass field validator

Models:
- ModelResolver: dataclass model resolver

Files:
- FileInfo: File info container
- FileList: Multiple file container

Response:
- Response: Response model decorator
- ResponseSerializer: Response serializer

Orchestration:
- ParamResolver: Parameter resolution orchestrator

Author: Cullinan
"""

from .base import Param, UNSET
from .types import Path, Query, Body, Header, File, RawBody
from .converter import TypeConverter, ConversionError
from .auto import Auto, AutoType
from .dynamic import DynamicBody, SafeAccessor, EMPTY
from .validator import ParamValidator, ValidationError
from .model import ModelResolver, ModelError
from .resolver import ParamResolver, ResolveError
from .file_info import FileInfo, FileList
from .dataclass_validators import (
    field_validator,
    FieldValidationError,
    validated_dataclass,
    validate_field,
    validate_dataclass,
)
from .response import (
    Response,
    ResponseModel,
    ResponseSerializer,
    serialize_response,
    get_response_models,
)
from .model_handlers import (
    ModelHandler,
    ModelHandlerError,
    ModelHandlerRegistry,
    DataclassHandler,
    get_model_handler_registry,
    reset_model_handler_registry,
)

__all__ = [
    # Base classes
    'Param',
    'UNSET',

    # Parameter types
    'Path',
    'Query',
    'Body',
    'Header',
    'File',
    'RawBody',

    # Type conversion
    'TypeConverter',
    'ConversionError',

    # Auto type
    'Auto',
    'AutoType',

    # Dynamic request body
    'DynamicBody',
    'SafeAccessor',
    'EMPTY',

    # Validation
    'ParamValidator',
    'ValidationError',

    # Models
    'ModelResolver',
    'ModelError',

    # Files
    'FileInfo',
    'FileList',

    # Dataclass validation
    'field_validator',
    'FieldValidationError',
    'validated_dataclass',
    'validate_field',
    'validate_dataclass',

    # Response
    'Response',
    'ResponseModel',
    'ResponseSerializer',
    'serialize_response',
    'get_response_models',

    # Model handlers (pluggable)
    'ModelHandler',
    'ModelHandlerError',
    'ModelHandlerRegistry',
    'DataclassHandler',
    'get_model_handler_registry',
    'reset_model_handler_registry',

    # Orchestration
    'ParamResolver',
    'ResolveError',
]

