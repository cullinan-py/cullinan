# -*- coding: utf-8 -*-
"""Cullinan Response Decorators

Response model decorator, used to define API response schemas.

Author: Cullinan
"""

from typing import Any, Type, List, Dict, Callable
from functools import wraps
import dataclasses
import json


class ResponseModel:
    """Response model definition

    Attributes:
        model: Response model class (dataclass or plain class)
        status_code: HTTP status code
        description: Response description
        content_type: Response content type
    """

    __slots__ = ('model', 'status_code', 'description', 'content_type', 'headers')

    def __init__(
        self,
        model: Type = None,
        status_code: int = 200,
        description: str = '',
        content_type: str = 'application/json',
        headers: Dict[str, str] = None,
    ):
        self.model = model
        self.status_code = status_code
        self.description = description
        self.content_type = content_type
        self.headers = headers or {}

    def __repr__(self) -> str:
        return (
            f"ResponseModel(model={self.model.__name__ if self.model else None}, "
            f"status_code={self.status_code})"
        )


def Response(
    model: Type = None,
    status_code: int = 200,
    description: str = '',
    content_type: str = 'application/json',
    headers: Dict[str, str] = None,
):
    """Response model decorator

    Used to define API endpoint response schemas, supports multiple response statuses.

    Args:
        model: Response model class
        status_code: HTTP status code
        description: Response description
        content_type: Response content type
        headers: Response headers

    Example:
        from dataclasses import dataclass
        from cullinan.web.params import Response

        @dataclass
        class UserResponse:
            id: int
            name: str
            email: str

        @dataclass
        class ErrorResponse:
            message: str
            code: int = 0

        @controller(url='/api/users')
        class UserController:
            @get_api(url='/{id}')
            @Response(model=UserResponse, status_code=200, description="User found")
            @Response(model=ErrorResponse, status_code=404, description="User not found")
            async def get_user(self, id: Path(int)):
                user = self.user_service.get(id)
                if not user:
                    return ErrorResponse(message="User not found"), 404
                return UserResponse(id=user.id, name=user.name, email=user.email)
    """
    response_model = ResponseModel(
        model=model,
        status_code=status_code,
        description=description,
        content_type=content_type,
        headers=headers,
    )

    def decorator(func: Callable) -> Callable:
        # Get or create response model list
        if not hasattr(func, '_response_models'):
            func._response_models = []

        func._response_models.append(response_model)

        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        # Preserve response model list
        wrapper._response_models = func._response_models

        return wrapper

    return decorator


def get_response_models(func: Callable) -> List[ResponseModel]:
    """Get the response model list for a function

    Args:
        func: The decorated function

    Returns:
        List of ResponseModel
    """
    return getattr(func, '_response_models', [])


class ResponseSerializer:
    """Response serializer

    Serializes response data to JSON format.
    Supports dataclass, dict, list and basic types.
    """

    @classmethod
    def serialize(cls, data: Any) -> Any:
        """Serialize response data

        Args:
            data: Response data

        Returns:
            JSON-serializable data
        """
        if data is None:
            return None

        # dataclass
        if dataclasses.is_dataclass(data) and not isinstance(data, type):
            return cls._serialize_dataclass(data)

        # dict
        if isinstance(data, dict):
            return {k: cls.serialize(v) for k, v in data.items()}

        # list/tuple
        if isinstance(data, (list, tuple)):
            return [cls.serialize(item) for item in data]

        # Basic types
        if isinstance(data, (str, int, float, bool)):
            return data

        # bytes
        if isinstance(data, bytes):
            return data.decode('utf-8', errors='replace')

        # Has to_dict method
        if hasattr(data, 'to_dict') and callable(data.to_dict):
            return cls.serialize(data.to_dict())

        # Has __dict__ attribute
        if hasattr(data, '__dict__'):
            return {k: cls.serialize(v) for k, v in data.__dict__.items()
                    if not k.startswith('_')}

        # Otherwise convert to string
        return str(data)

    @classmethod
    def _serialize_dataclass(cls, instance) -> dict:
        """Serialize dataclass instance

        Args:
            instance: dataclass instance

        Returns:
            dict
        """
        result = {}
        for field in dataclasses.fields(instance):
            value = getattr(instance, field.name)
            result[field.name] = cls.serialize(value)
        return result

    @classmethod
    def to_json(cls, data: Any, **kwargs) -> str:
        """Serialize to JSON string

        Args:
            data: Response data
            **kwargs: Arguments for json.dumps

        Returns:
            JSON string
        """
        serialized = cls.serialize(data)
        return json.dumps(serialized, ensure_ascii=False, **kwargs)


def serialize_response(data: Any) -> Any:
    """Convenience function to serialize response data

    Args:
        data: Response data

    Returns:
        JSON-serializable data
    """
    return ResponseSerializer.serialize(data)

