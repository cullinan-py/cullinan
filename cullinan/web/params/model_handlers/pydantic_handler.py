# -*- coding: utf-8 -*-
"""Cullinan Pydantic Model Handler

Optional Pydantic model handler.

Pydantic is an optional dependency; this module only works when Pydantic is available.

Author: Cullinan
"""

from typing import Any, Dict, Type

from .base import ModelHandler, ModelHandlerError


def _is_pydantic_available() -> bool:
    """Check if Pydantic is available"""
    try:
        import pydantic  # noqa: F401  (import is the availability probe)
        return True
    except ImportError:
        return False


def _get_pydantic_version() -> int:
    """Get Pydantic major version number"""
    try:
        import pydantic
        version_str = getattr(pydantic, 'VERSION', getattr(pydantic, '__version__', '1.0'))
        return int(version_str.split('.')[0])
    except Exception:
        return 0


class PydanticHandler(ModelHandler):
    """Pydantic model handler

    Optional handler for parsing Pydantic BaseModel.

    Features:
    - Supports Pydantic v1 and v2
    - Full Pydantic validation
    - Nested model resolution
    - Automatic type conversion

    Note:
        This handler is only available when Pydantic is installed.
    """

    priority = 50  # Higher than dataclass
    name = "pydantic"

    def __init__(self):
        if not _is_pydantic_available():
            raise ImportError("Pydantic is not installed")

        self._version = _get_pydantic_version()
        self._base_model = None
        self._load_pydantic()

    def _load_pydantic(self):
        """Load Pydantic"""
        from pydantic import BaseModel
        self._base_model = BaseModel

    def can_handle(self, type_: Type) -> bool:
        """Check if it is a Pydantic BaseModel"""
        if type_ is None:
            return False

        try:
            return isinstance(type_, type) and issubclass(type_, self._base_model)
        except Exception:
            return False

    def resolve(self, model_class: Type, data: Dict[str, Any]) -> Any:
        """Parse data into a Pydantic model instance"""
        if not self.can_handle(model_class):
            raise ModelHandlerError(
                f"{model_class} is not a Pydantic BaseModel",
                model_class=model_class,
                handler_name=self.name,
            )

        if data is None:
            data = {}

        try:
            if self._version >= 2:
                return model_class.model_validate(data)
            else:
                return model_class.parse_obj(data)
        except Exception as e:
            error_type = type(e).__name__
            if 'ValidationError' in error_type:
                raise ModelHandlerError(
                    f"Validation failed for {model_class.__name__}",
                    model_class=model_class,
                    errors=self._extract_errors(e),
                    handler_name=self.name,
                )
            raise ModelHandlerError(
                f"Failed to resolve {model_class.__name__}: {e}",
                model_class=model_class,
                handler_name=self.name,
            )

    def to_dict(self, instance: Any) -> Dict[str, Any]:
        """Convert Pydantic model instance to dict"""
        if self._version >= 2:
            return instance.model_dump()
        else:
            return instance.dict()

    def to_json(self, instance: Any) -> str:
        """Convert Pydantic model instance to JSON string"""
        if self._version >= 2:
            return instance.model_dump_json()
        else:
            return instance.json()

    def get_schema(self, model_class: Type) -> Dict[str, Any]:
        """Get the JSON Schema of a Pydantic model"""
        if not self.can_handle(model_class):
            raise ModelHandlerError(
                f"{model_class} is not a Pydantic BaseModel",
                model_class=model_class,
                handler_name=self.name,
            )

        if self._version >= 2:
            return model_class.model_json_schema()
        else:
            return model_class.schema()

    def _extract_errors(self, error) -> list:
        """Extract error information from a Pydantic ValidationError"""
        errors = []
        try:
            for err in error.errors():
                errors.append({
                    'loc': list(err.get('loc', [])),
                    'msg': err.get('msg', ''),
                    'type': err.get('type', ''),
                })
        except Exception:
            errors.append({'msg': str(error)})
        return errors

