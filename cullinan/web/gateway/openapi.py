# -*- coding: utf-8 -*-
"""Cullinan OpenAPI 3.0 Schema Generator

Introspects the gateway ``Router`` to auto-generate an OpenAPI 3.0.3 specification
from registered routes, parameter annotations, and controller docstrings.

Usage::

    from cullinan.web.gateway import get_router
    from cullinan.web.gateway.openapi import OpenAPIGenerator

    gen = OpenAPIGenerator(router=get_router(), title='My API', version='1.0.0')
    spec = gen.to_dict()          # OpenAPI dict
    json_str = gen.to_json()      # JSON string
    yaml_str = gen.to_yaml()      # YAML string (requires PyYAML)

    # Register built-in /openapi.json endpoint
    gen.register_spec_routes()

Author: plumeink
"""

import inspect
import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Type

from .router import Router
from .route_types import RouteEntry

logger = logging.getLogger(__name__)

# Python type → OpenAPI type/format mapping
_TYPE_MAP: Dict[type, Dict[str, str]] = {
    str:   {'type': 'string'},
    int:   {'type': 'integer', 'format': 'int64'},
    float: {'type': 'number', 'format': 'double'},
    bool:  {'type': 'boolean'},
    bytes: {'type': 'string', 'format': 'binary'},
    list:  {'type': 'array'},
    dict:  {'type': 'object'},
}


class OpenAPIGenerator:
    """Generate an OpenAPI 3.0.3 specification from a Cullinan Router.

    Attributes:
        router: The gateway ``Router`` whose routes are introspected.
        title: API title.
        version: API version string.
        description: Optional API description.
        servers: Optional list of server objects.
    """

    def __init__(
        self,
        router: Optional[Router] = None,
        title: str = 'Cullinan API',
        version: str = '1.0.0',
        description: str = '',
        servers: Optional[List[Dict[str, str]]] = None,
    ) -> None:
        if router is None:
            from .globals import get_router
            router = get_router()
        self._router = router
        self._title = title
        self._version = version
        self._description = description
        self._servers = servers or []
        self._extra_schemas: Dict[str, Dict] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Generate the full OpenAPI 3.0.3 specification as a dict."""
        spec: Dict[str, Any] = {
            'openapi': '3.0.3',
            'info': {
                'title': self._title,
                'version': self._version,
            },
            'paths': {},
        }
        if self._description:
            spec['info']['description'] = self._description
        if self._servers:
            spec['servers'] = self._servers

        # Build paths
        routes = self._router.get_all_routes()
        paths: Dict[str, Dict[str, Any]] = {}
        used_tags: Set[str] = set()

        for entry in routes:
            if entry.path in ('/openapi.json', '/openapi.yaml'):
                continue  # skip spec endpoint itself

            oa_path = self._to_openapi_path(entry.path)
            method = entry.method.lower()
            if method == '*':
                method = 'get'

            if oa_path not in paths:
                paths[oa_path] = {}

            operation = self._build_operation(entry)
            paths[oa_path][method] = operation

            for tag in operation.get('tags', []):
                used_tags.add(tag)

        spec['paths'] = paths

        # Tags
        if used_tags:
            spec['tags'] = [{'name': t} for t in sorted(used_tags)]

        # Schemas
        if self._extra_schemas:
            spec.setdefault('components', {})['schemas'] = dict(self._extra_schemas)

        return spec

    def to_json(self, indent: int = 2) -> str:
        """Serialize the spec to JSON."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, default=str)

    def to_yaml(self) -> str:
        """Serialize the spec to YAML (requires PyYAML)."""
        try:
            import yaml
        except ImportError:
            raise ImportError(
                "PyYAML is required for YAML output. Install it with: pip install pyyaml"
            )
        return yaml.dump(self.to_dict(), allow_unicode=True, sort_keys=False, default_flow_style=False)

    def register_spec_routes(self, router: Optional[Router] = None) -> None:
        """Register ``/openapi.json`` (and optionally ``/openapi.yaml``) endpoints.

        Args:
            router: Router to register routes on (defaults to self._router).
        """
        target_router = router or self._router
        generator = self  # capture reference

        async def _serve_json(request: Any) -> Any:
            from .web_core import WebResponse
            return WebResponse(
                body=generator.to_json(),
                status_code=200,
                content_type='application/json',
            )

        async def _serve_yaml(request: Any) -> Any:
            from .web_core import WebResponse
            try:
                content = generator.to_yaml()
                return WebResponse(
                    body=content,
                    status_code=200,
                    content_type='text/yaml; charset=utf-8',
                )
            except ImportError:
                return WebResponse.error(
                    501, 'YAML output requires PyYAML: pip install pyyaml'
                )

        target_router.add_route('GET', '/openapi.json', handler=_serve_json,
                                metadata={'hidden': True})
        target_router.add_route('GET', '/openapi.yaml', handler=_serve_yaml,
                                metadata={'hidden': True})
        logger.info('OpenAPI spec endpoints registered: /openapi.json, /openapi.yaml')

    def add_schema(self, name: str, schema: Dict[str, Any]) -> None:
        """Add a reusable component schema.

        Args:
            name: Schema name (e.g. ``'UserDTO'``).
            schema: JSON Schema object.
        """
        self._extra_schemas[name] = schema

    # ------------------------------------------------------------------
    # Internal: build an operation object for a RouteEntry
    # ------------------------------------------------------------------

    def _build_operation(self, entry: RouteEntry) -> Dict[str, Any]:
        """Build an OpenAPI operation object from a ``RouteEntry``."""
        operation: Dict[str, Any] = {}

        # Tags — derive from controller class name
        tags = entry.metadata.get('tags')
        if tags:
            operation['tags'] = tags if isinstance(tags, list) else [tags]
        elif entry.controller_cls:
            tag = self._controller_tag(entry.controller_cls)
            operation['tags'] = [tag]

        # Summary & description — from metadata or docstring
        summary = entry.metadata.get('summary', '')
        description = entry.metadata.get('description', '')

        if not summary and entry.handler:
            doc = inspect.getdoc(entry.handler)
            if doc:
                lines = doc.strip().split('\n')
                summary = lines[0].strip()
                if len(lines) > 1:
                    description = '\n'.join(l.strip() for l in lines[1:]).strip()

        if summary:
            operation['summary'] = summary
        if description:
            operation['description'] = description

        # operationId
        op_id = entry.metadata.get('operationId')
        if not op_id:
            op_id = self._make_operation_id(entry)
        operation['operationId'] = op_id

        # Deprecated
        if entry.metadata.get('deprecated'):
            operation['deprecated'] = True

        # Parameters & request body
        parameters, request_body = self._extract_params(entry)
        if parameters:
            operation['parameters'] = parameters
        if request_body:
            operation['requestBody'] = request_body

        # Responses (default)
        operation['responses'] = entry.metadata.get('responses') or {
            '200': {'description': 'Successful response'},
        }

        return operation

    # ------------------------------------------------------------------
    # Parameter extraction
    # ------------------------------------------------------------------

    def _extract_params(
        self, entry: RouteEntry,
    ) -> Tuple[List[Dict], Optional[Dict]]:
        """Extract OpenAPI parameters and requestBody from handler signature.

        Inspects the handler callable's type annotations for ``Param`` subclass
        instances (``Path``, ``Query``, ``Header``, ``Body``, ``File``).
        Falls back to ``param_names`` for path parameters.
        """
        parameters: List[Dict] = []
        request_body: Optional[Dict] = None

        handler = entry.handler
        if handler is None:
            # Fallback: just path params from entry
            for pname in entry.param_names:
                parameters.append({
                    'name': pname,
                    'in': 'path',
                    'required': True,
                    'schema': {'type': 'string'},
                })
            return parameters, request_body

        # Try to get signature
        try:
            sig = inspect.signature(handler)
        except (ValueError, TypeError):
            for pname in entry.param_names:
                parameters.append({
                    'name': pname,
                    'in': 'path',
                    'required': True,
                    'schema': {'type': 'string'},
                })
            return parameters, request_body

        body_props: Dict[str, Any] = {}
        body_required_fields: List[str] = []
        seen_path_params: Set[str] = set()

        for pname, param in sig.parameters.items():
            if pname == 'self':
                continue

            # Check if default is a Param instance
            default = param.default
            param_spec = None

            try:
                from cullinan.web.params.base import Param as ParamBase
                if isinstance(default, ParamBase):
                    param_spec = default
            except ImportError:
                pass

            if param_spec is not None:
                source = param_spec.source
                schema = self._type_to_schema(param_spec.type_)
                self._apply_constraints(schema, param_spec)

                if source == 'path':
                    seen_path_params.add(pname)
                    parameters.append({
                        'name': param_spec.alias or param_spec.name or pname,
                        'in': 'path',
                        'required': True,
                        'schema': schema,
                        **(
                            {'description': param_spec.description}
                            if param_spec.description else {}
                        ),
                    })
                elif source == 'query':
                    p: Dict[str, Any] = {
                        'name': param_spec.alias or param_spec.name or pname,
                        'in': 'query',
                        'required': param_spec.required,
                        'schema': schema,
                    }
                    if param_spec.description:
                        p['description'] = param_spec.description
                    if param_spec.has_default():
                        schema['default'] = param_spec.get_default()
                    parameters.append(p)
                elif source == 'header':
                    p = {
                        'name': param_spec.alias or param_spec.name or pname,
                        'in': 'header',
                        'required': param_spec.required,
                        'schema': schema,
                    }
                    if param_spec.description:
                        p['description'] = param_spec.description
                    parameters.append(p)
                elif source in ('body', 'auto'):
                    prop_schema = schema.copy()
                    if param_spec.description:
                        prop_schema['description'] = param_spec.description
                    body_props[param_spec.alias or param_spec.name or pname] = prop_schema
                    if param_spec.required:
                        body_required_fields.append(param_spec.alias or param_spec.name or pname)
                elif source == 'file':
                    body_props[param_spec.alias or param_spec.name or pname] = {
                        'type': 'string', 'format': 'binary',
                    }
                # else: unknown source, skip
            else:
                # No Param annotation — check if name matches a path param
                if pname in entry.param_names:
                    seen_path_params.add(pname)
                    ann_type = param.annotation if param.annotation != inspect.Parameter.empty else str
                    parameters.append({
                        'name': pname,
                        'in': 'path',
                        'required': True,
                        'schema': self._type_to_schema(ann_type),
                    })

        # Add any remaining path params not captured by annotation
        for pname in entry.param_names:
            if pname not in seen_path_params:
                parameters.append({
                    'name': pname,
                    'in': 'path',
                    'required': True,
                    'schema': {'type': 'string'},
                })

        # Build requestBody if we found body params
        if body_props:
            body_schema: Dict[str, Any] = {
                'type': 'object',
                'properties': body_props,
            }
            if body_required_fields:
                body_schema['required'] = body_required_fields
            request_body = {
                'required': True,
                'content': {
                    'application/json': {
                        'schema': body_schema,
                    },
                },
            }

        return parameters, request_body

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_openapi_path(path: str) -> str:
        """Convert gateway path template to OpenAPI path format.

        Gateway uses ``{name}`` which is already OpenAPI-compatible.
        Regex patterns ``{name:pattern}`` are stripped of the pattern portion.
        """
        return re.sub(r'\{(\w+):[^}]+}', r'{\1}', path)

    @staticmethod
    def _controller_tag(cls: Type) -> str:
        """Derive an OpenAPI tag from a controller class name."""
        name = cls.__name__
        # Remove 'Controller' suffix
        if name.endswith('Controller'):
            name = name[:-len('Controller')]
        return name

    @staticmethod
    def _make_operation_id(entry: RouteEntry) -> str:
        """Generate an operationId from method and path."""
        method = entry.method.lower()
        path_parts = [s for s in entry.path.split('/') if s and not s.startswith('{')]
        name_parts = [method] + path_parts
        if entry.controller_method_name:
            return entry.controller_method_name
        return '_'.join(name_parts)

    @staticmethod
    def _type_to_schema(py_type: Any) -> Dict[str, Any]:
        """Convert a Python type to a JSON Schema fragment."""
        if py_type is None or py_type is inspect.Parameter.empty:
            return {'type': 'string'}
        schema = _TYPE_MAP.get(py_type)
        if schema:
            return dict(schema)
        # Check for Optional, List, etc.
        origin = getattr(py_type, '__origin__', None)
        if origin is list or origin is List:
            args = getattr(py_type, '__args__', None)
            item_schema = {'type': 'string'}
            if args:
                item_schema = OpenAPIGenerator._type_to_schema(args[0])
            return {'type': 'array', 'items': item_schema}
        # Fallback
        return {'type': 'string'}

    @staticmethod
    def _apply_constraints(schema: Dict[str, Any], param_spec: Any) -> None:
        """Apply Param constraints to a JSON Schema."""
        if getattr(param_spec, 'ge', None) is not None:
            schema['minimum'] = param_spec.ge
        if getattr(param_spec, 'le', None) is not None:
            schema['maximum'] = param_spec.le
        if getattr(param_spec, 'gt', None) is not None:
            schema['exclusiveMinimum'] = param_spec.gt
        if getattr(param_spec, 'lt', None) is not None:
            schema['exclusiveMaximum'] = param_spec.lt
        if getattr(param_spec, 'min_length', None) is not None:
            schema['minLength'] = param_spec.min_length
        if getattr(param_spec, 'max_length', None) is not None:
            schema['maxLength'] = param_spec.max_length
        if getattr(param_spec, 'regex', None) is not None:
            schema['pattern'] = param_spec.regex
