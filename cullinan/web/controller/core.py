# python
# -*- coding: utf-8 -*-

import json
import inspect
import functools
import contextvars
import logging
import time
import os
from cullinan.core.services.registry import get_service_registry
from cullinan.web.controller.registry import get_controller_registry
from cullinan.support.exceptions import (
    HandlerError, MissingHeaderException
)
from cullinan.web.handler.base import BaseHandler
from typing import Callable, Optional, Sequence, Tuple, TYPE_CHECKING, Any, Protocol, List

# New parameter system imports
from cullinan.web.params import DynamicBody, ParamResolver, ResolveError

class ResponseProtocol(Protocol):
    def push(self, resp: Any) -> Any: ...
    def pop(self, token: Any) -> None: ...
    def get(self) -> Any: ...

if TYPE_CHECKING:
    # help static analyzers: at type-check time `response` behaves like ResponseProtocol
    response: ResponseProtocol

logger = logging.getLogger(__name__)
# access logger (separate name so users can configure access logs separately)
access_logger = logging.getLogger('cullinan.access')


# ============================================================================
# Registry Pattern Integration (Direct Registry Usage)
# ============================================================================
# Global lists have been completely replaced with registry pattern.
# Use get_header_registry() and get_controller_registry() for all operations.

# Context variable for controller method collection during decoration (thread-safe)
# This is used during controller class decoration to collect methods
_controller_decoration_context: contextvars.ContextVar[Optional[List]] = contextvars.ContextVar(
    '_controller_decoration_context', default=None
)

KEY_NAME_INDEX = {
    "url_params": 0,
    "query_params": 1,
    "body_params": 2,
    "file_params": 3,
}

# Performance optimization: cache function signatures to avoid repeated inspect.signature() calls
_SIGNATURE_CACHE = {}
# Performance optimization: cache parameter mappings to avoid repeated list comprehension
_PARAM_MAPPING_CACHE = {}
# Performance optimization: cache URL pattern resolution to avoid repeated parsing
_URL_PATTERN_CACHE = {}


# ============================================================================
# Header Registry
# ============================================================================
class HeaderRegistry:
    """Registry for global HTTP headers.

    Manages headers that should be applied to all HTTP responses.
    Provides methods for registration and retrieval of headers.
    """

    def __init__(self):
        """Initialize an empty header registry."""
        self._headers: List[Any] = []

    def register(self, header: Any) -> None:
        """Register a global header to be applied to all responses.

        Args:
            header: Header object or tuple to be added to responses
        """
        self._headers.append(header)
        logger.debug(f"Registered global header: {header}")

    def get_headers(self) -> List[Any]:
        """Get all registered headers.

        Returns:
            List of header objects/tuples
        """
        return self._headers.copy()

    def clear(self) -> None:
        """Clear all registered headers.

        Useful for testing or application reinitialization.
        """
        self._headers.clear()
        logger.debug("Cleared all registered headers")

    def count(self) -> int:
        """Get the number of registered headers.

        Returns:
            Number of registered global headers
        """
        return len(self._headers)

    def has_headers(self) -> bool:
        """Check if any headers are registered.

        Returns:
            True if headers exist, False otherwise
        """
        return len(self._headers) > 0


# Global header registry instance
_default_header_registry = HeaderRegistry()


def get_header_registry() -> HeaderRegistry:
    """Get the default global header registry.

    Returns:
        The default HeaderRegistry instance
    """
    return _default_header_registry


# ============================================================================
# Missing Header Handler Hook
# ============================================================================
# Default handler for missing required headers - raises MissingHeaderException
def _default_missing_header_handler(request, header_name: str):
    """Default handler for missing required headers.

    Args:
        request: The request object (Controller instance)
        header_name: Name of the missing header

    Raises:
        MissingHeaderException: Always raised by default
    """
    raise MissingHeaderException(header_name=header_name)


# Global missing header handler hook
_missing_header_handler = _default_missing_header_handler


def set_missing_header_handler(handler: Callable[[Any, str], None]):
    """Set custom missing header handler.

    Args:
        handler: Callable that takes (request, header_name) and handles the missing header

    Example:
        def custom_handler(request, header_name):
            request.write_error(400, message=f"Missing header: {header_name}")

        set_missing_header_handler(custom_handler)
    """
    global _missing_header_handler
    _missing_header_handler = handler


def get_missing_header_handler() -> Callable[[Any, str], None]:
    """Get current missing header handler.

    Returns:
        The current missing header handler function
    """
    return _missing_header_handler


def _get_cached_signature(func: Callable) -> inspect.Signature:
    """Get cached function signature to avoid repeated inspect.signature() calls.
    
    This optimization significantly reduces overhead in request handling by caching
    the inspection results for each function.
    """
    if func not in _SIGNATURE_CACHE:
        _SIGNATURE_CACHE[func] = inspect.signature(func)
    return _SIGNATURE_CACHE[func]


def _get_cached_param_mapping(func: Callable) -> Tuple[list, bool, bool]:
    """Get cached parameter mapping for a function.
    
    Returns a tuple of (param_names, needs_request_body, needs_headers) to avoid
    repeated parameter name extraction and checking on every request.
    """
    if func not in _PARAM_MAPPING_CACHE:
        sig = _get_cached_signature(func)
        param_names = [p.name for p in sig.parameters.values()
                       if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)]
        if param_names and param_names[0] == 'self':
            param_names = param_names[1:]
        
        # Pre-check if function needs special parameters
        needs_request_body = 'request_body' in param_names
        needs_headers = 'headers' in param_names
        
        _PARAM_MAPPING_CACHE[func] = (param_names, needs_request_body, needs_headers)
    
    return _PARAM_MAPPING_CACHE[func]


class ResponseProxy:
    """
    contextvars `ContextVar` proxy, used as the module-level response.
    - push(resp) binds the instance, returns a token (used for reset)
    - pop(token) restores the context
    - get() gets the current instance (may be None)
    - __getattr__ delegates to the current instance, so existing code can call response.xxx directly
    """
    def __init__(self):
        self._ctx = contextvars.ContextVar("cullinan_response", default=None)

    def push(self, resp):
        return self._ctx.set(resp)

    def pop(self, token):
        try:
            self._ctx.reset(token)
        except Exception:
            pass

    def get(self):
        return self._ctx.get()

    def _ensure(self):
        resp = self.get()
        if resp is None:
            raise RuntimeError("no Response bound in this context")
        return resp

    def __getattr__(self, name):
        return getattr(self._ensure(), name)


class LazyResponseMeta(type):
    """
    Metaclass: treats the module name `response` as a lazy proxy class object.
    - Does not instantiate the real proxy at import time
    - Creates and caches a ResponseProxy instance on first read or write of a non-private member
    """
    def __getattribute__(cls, name):
        # Private or meta attributes still use the class itself
        if name.startswith('_'):
            return super().__getattribute__(name)
        inst = cls.__dict__.get('_instance', None)
        if inst is None:
            inst = ResponseProxy()
            super().__setattr__('_instance', inst)
        return getattr(inst, name)

    def __setattr__(cls, name, value):
        if name.startswith('_'):
            return super().__setattr__(name, value)
        inst = cls.__dict__.get('_instance', None)
        if inst is None:
            inst = ResponseProxy()
            super().__setattr__('_instance', inst)
        setattr(inst, name, value)

    def __repr__(cls):
        inst = cls.__dict__.get('_instance', None)
        if inst is None:
            return "<lazy response (not initialized)>"
        return repr(inst)


# Module-level lazy proxy class named `response` (*not an instance*, to avoid side effects at import time)
class response(metaclass=LazyResponseMeta):
    """Lazy response proxy class (module-level name, behaves identically to the original ResponseProxy instance)"""

    # Stubs to help static analysis / IDEs detect available methods (runtime is handled by metaclass).
    def push(self, resp):
        """Stub: real implementation lives in the lazily created ResponseProxy instance."""
        raise RuntimeError("response proxy not initialized")

    def pop(self, token):
        raise RuntimeError("response proxy not initialized")

    def get(self):
        raise RuntimeError("response proxy not initialized")

    def __getattr__(self, name):
        # stub fallback
        raise AttributeError(name)


class EncapsulationHandler(object):
    @classmethod
    def set_fragment_method(cls, cls_obj: Any, func: Callable[[object, tuple, dict], None]):
        """Wraps a function as an async method and binds it to the class.

        Uses a unified async def wrapper, checks at runtime whether the result needs to be awaited.
        This ensures correct handling whether the original function is sync or async.

        CRITICAL FIX: Uses a unified async wrapper + inspect.isawaitable() runtime check
        - Simplifies logic, avoids branch conditions
        - Uses isawaitable() to cover all awaitable object types
        - Tornado fully supports this unified async approach
        """
        @functools.wraps(func)
        async def dummy(self, *args, **kwargs):
            result = func(self, *args, **kwargs)
            # Check if result is an awaitable (coroutine, generator-based coroutine, custom awaitable, Future)
            if inspect.isawaitable(result):
                result = await result
            return result

        setattr(cls_obj, func.__name__, dummy)


    @staticmethod
    def add_func(url: str, type: str) -> Callable:
        """Register a controller method for the currently decorating controller.

        Args:
            url: URL pattern for this method
            type: HTTP method type (get, post, put, delete, etc.)

        Returns:
            Decorator function
        """
        def inner(func: Callable):
            # Get the current decoration context (set by @controller decorator)
            func_list = _controller_decoration_context.get()
            if func_list is None:
                # Fallback: if no context, create a temporary list and set it
                func_list = []
                _controller_decoration_context.set(func_list)
            func_list.append((url, func, type))
            return func

        return inner



class Handler(BaseHandler):
    """Transport-agnostic compatibility handler base."""

    @classmethod
    def set_instance_method(cls, cls_name, func):
        """Forwarder used by the dynamic servlet factory so static analysis can see the method.

        The real registration uses EncapsulationHandler.set_fragment_method which sets an instance
        method on the class; this forwarder simply calls that implementation.
        """
        EncapsulationHandler.set_fragment_method(cls_name, func)

    def data_received(self, chunk):
        pass

    def set_default_headers(self):
        # Use header registry instead of global list
        header_registry = get_header_registry()
        setter = getattr(self, "set_header", None)
        if callable(setter) and header_registry.has_headers():
            for header in header_registry.get_headers():
                setter(header[0], header[1])

    def options(self):
        pass


def request_resolver(self,
                     url_param_key_list: Optional[Sequence] = None,
                     url_param_value_list: Optional[Sequence] = None,
                     query_param_names: Optional[Sequence] = None,
                     body_param_names: Optional[Sequence] = None,
                     file_param_key_list: Optional[Sequence] = None) -> Tuple[Optional[dict], Optional[dict], Optional[dict], Optional[dict]]:
    """
    Unified resolver: accept optional sequences and normalize them to concrete tuples/lists.
    Returns (url_dict|None, query_dict|None, body_dict|None, file_dict|None).
    """
    # normalize inputs to concrete sequences
    url_param_key_list = tuple(url_param_key_list or ())
    url_param_value_list = tuple(url_param_value_list or ())
    query_param_names = tuple(query_param_names or ())
    body_param_names = tuple(body_param_names or ())
    file_param_key_list = list(file_param_key_list or [])

    url_dict = None
    query_dict = None
    body_dict = None
    file_dict = None

    # URL params
    if url_param_key_list:
        url_dict = {}
        for i, k in enumerate(url_param_key_list):
            try:
                url_dict[k] = url_param_value_list[i]
            except Exception:
                url_dict[k] = None
        # Conditional logging: only format string if INFO level is enabled
        if logger.isEnabledFor(logging.INFO):
            logger.info("\t||| url_params %s", url_dict)

    # Query params
    if query_param_names:
        query_dict = {}
        for name in query_param_names:
            try:
                query_dict[name] = self.get_query_argument(name)
            except Exception:
                query_dict[name] = None
        # Conditional logging: only format string if INFO level is enabled
        if logger.isEnabledFor(logging.INFO):
            logger.info("\t||| query_params %s", query_dict)

    # Body params
    if body_param_names:
        body_dict = {}
        # Optimized content-type checking - avoid unnecessary string operations
        ctype = self.request.headers.get('Content-Type', '')
        # Check first 16 chars (length of 'application/json') case-insensitively
        is_json = ctype[:16].lower() == 'application/json' if len(ctype) >= 16 else ctype.lower().startswith('application/json')
        if is_json:
            try:
                raw = self.request.body or b'{}'
                data = json.loads(raw)
            except Exception:
                data = {}
            for name in body_param_names:
                body_dict[name] = data.get(name)
        else:
            for name in body_param_names:
                try:
                    body_dict[name] = self.get_body_argument(name)
                except Exception:
                    body_dict[name] = None
        # Conditional logging: only format string if INFO level is enabled
        if logger.isEnabledFor(logging.INFO):
            logger.info("\t||| body_params %s", body_dict)

    # File params
    if file_param_key_list:
        file_dict = {}
        for name in file_param_key_list:
            file_dict[name] = (self.request.files.get(name) if isinstance(self.request.files, dict) else None)
        # Conditional logging: only format string if INFO level is enabled
        if logger.isEnabledFor(logging.INFO):
            logger.info("\t||| file_params %s", list((file_dict or {}).keys()))

    return url_dict, query_dict, body_dict, file_dict


def header_resolver(self, header_names: Optional[Sequence] = None) -> Optional[dict]:
    """Resolve required headers from the request.
    
    Optimized to reduce loop overhead and unnecessary conversions.
    """
    if not header_names:
        return None
    
    headers_dict = self.request.headers
    need_header = {}
    missing_headers = []
    
    # Single pass to collect headers and identify missing ones
    for name in header_names:
        value = headers_dict.get(name)
        need_header[name] = value
        if value is None:
            missing_headers.append(name)
    
    # Batch logging for present headers (if enabled)
    if logger.isEnabledFor(logging.INFO):
        present = {k: v for k, v in need_header.items() if v is not None}
        if present:
            logger.info("\t||| request_headers %s", present)
    
    # Handle missing headers
    if missing_headers:
        miss_header_handler = get_missing_header_handler()
        for name in missing_headers:
            miss_header_handler(self, name)

    return need_header


def url_resolver(url: str) -> Tuple[str, list]:
    """Parse URL template with parameters and return regex pattern and parameter names.
    
    Uses caching to avoid repeated parsing of the same URL patterns.
    
    Args:
        url: URL template with parameters in {param_name} format
        
    Returns:
        Tuple of (regex_pattern, param_names_list)
        
    Example:
        url_resolver("/user/{id}/post/{post_id}") 
        -> ("/user/([a-zA-Z0-9-]+)/*/post/([a-zA-Z0-9-]+)/*", ["id", "post_id"])
    """
    # Check cache first
    if url in _URL_PATTERN_CACHE:
        return _URL_PATTERN_CACHE[url]
    
    # Parse URL pattern
    find_all = lambda origin, target: [i for i in range(origin.find(target), len(origin)) if origin[i] == target]
    before_list = find_all(url, "{")
    after_list = find_all(url, "}")
    url_param_list = []
    for index in range(0, len(before_list)):
        url_param_list.append(url[int(before_list[index]) + 1:int(after_list[index])])
    for url_param in url_param_list:
        url = url.replace(url_param, "[a-zA-Z0-9-]+")
    url = url.replace("{", "(").replace("}", ")/*")
    
    # Cache result
    result = (url, url_param_list)
    _URL_PATTERN_CACHE[url] = result
    return result


class _SimpleResponse:
    """Fallback minimal response implementing the expected interface with memory optimization.
    
    This class uses __slots__ to reduce memory overhead and provides a simple
    interface compatible with HttpResponse for fallback scenarios.
    """
    __slots__ = ('_headers', '_status', '_body')
    
    def __init__(self) -> None:
        self._headers: list = []
        self._status: int = 200
        self._body: str = ''

    def get_headers(self) -> list:
        """Return a copy of the response headers list."""
        return list(self._headers)

    def get_status(self) -> int:
        """Return the HTTP status code."""
        return self._status

    def get_body(self) -> str:
        """Return the response body."""
        return self._body


def emit_access_log(request: Any, resp_obj: Optional[Any], status_code: Optional[int], duration: float) -> None:
    """Emit an access log using the configured format.

    Formats supported via env var CULLINAN_ACCESS_LOG_FORMAT:
      - 'combined' (default): Apache combined-like format
      - 'json': structured JSON object

    Args:
        request: The HTTP request object or handler-like request wrapper
        resp_obj: The response object (HttpResponse or compatible)
        status_code: HTTP status code
        duration: Request processing time in seconds
        
    This helper is public for testing or custom hooks; the framework calls it
    automatically from request_handler.
    """
    try:
        fmt = os.getenv('CULLINAN_ACCESS_LOG_FORMAT', 'combined').strip().lower()
        method = getattr(request, 'method', '-')
        uri = getattr(request, 'uri', getattr(request, 'path', '-'))
        client = getattr(request, 'remote_ip', None) or getattr(request, 'remote_addr', None) or getattr(request, 'remote_ip', None) or '-'
        # headers may be present on transport-native request objects
        headers = getattr(request, 'headers', {}) or {}
        referer = headers.get('Referer', headers.get('referer', '-'))
        user_agent = headers.get('User-Agent', headers.get('user-agent', '-'))
        # content length from response object if available
        content_length = '-'
        try:
            if resp_obj is not None and hasattr(resp_obj, 'get_body'):
                body = resp_obj.get_body()
                if isinstance(body, (bytes, bytearray)):
                    content_length = len(body)
                elif isinstance(body, str):
                    content_length = len(body.encode('utf-8'))
                elif hasattr(body, '__len__'):
                    content_length = len(body)
        except Exception:
            content_length = '-'

        if fmt == 'json':
            obj = {
                'remote_addr': client,
                'method': method,
                'path': uri,
                'status_code': status_code,
                'duration': round(duration, 3),
                'content_length': content_length,
                'referer': referer or '-',
                'user_agent': user_agent or '-',
            }
            access_logger.info(json.dumps(obj, ensure_ascii=False))
        else:
            # combined-like: remote - - [time] "METHOD URI HTTP/1.1" status length "referer" "user-agent" duration
            now = time.strftime('%d/%b/%Y:%H:%M:%S')
            line = '%s - - [%s] "%s %s HTTP/1.1" %s %s "%s" "%s" %.3f' % (
                client, now, method, uri, status_code or '-', content_length, referer or '-', user_agent or '-', duration)
            access_logger.info(line)
    except Exception as e:
        logger.error('[ACCESS_LOG_FORMAT_ERROR] Failed to format access log: %s', str(e), exc_info=True)


async def request_handler(self, func: Callable, params: Tuple, headers: Optional[dict],
                          type: str, get_request_body: bool = False,
                          url_param_keys: list = None, url_param_values: tuple = None) -> None:
    """Handle HTTP request by invoking the controller function with resolved parameters.
    
    This is the core request handling function that:
    1. Selects the appropriate controller instance based on HTTP method
    2. Injects service and response objects
    3. Resolves and maps parameters from the request
    4. Invokes the controller function (supports both sync and async)
    5. Writes the response
    6. Emits access logs
    
    Args:
        self: The transport-native handler or request wrapper instance
        func: The controller function to invoke (can be sync or async)
        params: Tuple of (url_params, query_params, body_params, file_params)
        headers: Dictionary of required headers
        type: HTTP method type ('get', 'post', 'patch', 'delete', 'put')
        get_request_body: Whether to pass raw request body to the function
        url_param_keys: List of URL parameter names (for new param system)
        url_param_values: Tuple of URL parameter values (for new param system)

    Performance optimizations:
        - Uses cached function signatures (_get_cached_signature)
        - Uses cached parameter mappings (_get_cached_param_mapping)
        - Conditional logging to reduce overhead
        - Automatic async/await handling for async controller methods
    """
    global controller_self
    start_time = time.time()

    # [HOT] Critical fix: get Controller class from factory and instantiate
    # This way @injectable auto-injects dependencies, and InjectByName descriptor works properly
    if type == 'get':
        controller_factory = getattr(self, 'get_controller_factory', None) or getattr(self, 'get_controller_self', None)
    elif type == 'post':
        controller_factory = getattr(self, 'post_controller_factory', None) or getattr(self, 'post_controller_self', None)
    elif type == 'patch':
        controller_factory = getattr(self, 'patch_controller_factory', None) or getattr(self, 'patch_controller_self', None)
    elif type == 'delete':
        controller_factory = getattr(self, 'delete_controller_factory', None) or getattr(self, 'delete_controller_self', None)
    elif type == 'put':
        controller_factory = getattr(self, 'put_controller_factory', None) or getattr(self, 'put_controller_self', None)
    else:
        raise HandlerError(
            "Unsupported request type",
            error_code="INVALID_REQUEST_TYPE",
            details={"type": type, "allowed_types": ["get", "post", "patch", "delete", "put"]}
        )

    if controller_factory is None:
        raise HandlerError(
            "Controller factory not found",
            error_code="CONTROLLER_NOT_REGISTERED",
            details={"type": type}
        )

    # [SINGLETON] Get singleton instance from ControllerRegistry
    # Instead of creating a new instance per request
    # @injectable auto-injects dependencies on first creation
    try:
        controller_registry = get_controller_registry()
        controller_name = controller_factory.__name__
        controller_self = controller_registry.get_instance(controller_name)

        if controller_self is None:
            raise HandlerError(
                "Controller instance not found",
                error_code="CONTROLLER_NOT_FOUND",
                details={"controller": controller_name, "type": type}
            )

        logger.debug(f"Using controller singleton: {controller_name}")
    except Exception as e:
        logger.error(f"Failed to get controller {controller_factory.__name__}: {e}", exc_info=True)
        raise HandlerError(
            "Controller retrieval failed",
            error_code="CONTROLLER_GET_ERROR",
            details={"controller": controller_factory.__name__, "error": str(e)}
        )

    # Inject service and module-level proxy (controller methods can still access self.response)
    # Use new service registry - provide instance dict access for backward compatibility
    service_registry = get_service_registry()
    setattr(controller_self, 'service', service_registry.list_instances())
    setattr(controller_self, 'response', response)
    setattr(controller_self, 'response_factory', response_build)

    # Construct real response instance (use pooling if enabled, otherwise response_build)
    resp_instance = None
    try:
        # Try to get pooled response first if pooling is enabled
        resp_instance = get_pooled_response()
        if resp_instance is None:
            if callable(response_build):
                resp_instance = response_build()
            else:
                resp_instance = response_build
    except Exception as e:
        logger.error(
            '[RESPONSE_BUILD_ERROR] response_build failed, falling back to _SimpleResponse: %s',
            str(e),
            exc_info=True
        )
        resp_instance = _SimpleResponse()

    if resp_instance is None:
        resp_instance = _SimpleResponse()

    # Bind to contextvars, return token
    token = response.push(resp_instance)

    # Initialize resp_obj to avoid UnboundLocalError in exception handler
    resp_obj = None

    try:
        # =================================================================
        # New Parameter System Integration (v0.90+)
        # =================================================================
        # Check if function uses new-style parameter annotations (Path, Query, Body, DynamicBody, etc.)
        # If so, use ParamResolver; otherwise fall back to legacy parameter handling

        use_new_param_system = False
        params_config = {}

        try:
            params_config = ParamResolver.analyze_params(func)
            # Check if any parameter uses the new system
            for name, config in params_config.items():
                source = config.get('source', 'unknown')
                target_type = config.get('type')
                param_spec = config.get('param_spec')
                # New system markers: Param subclass instance, DynamicBody, or dataclass
                if param_spec is not None or target_type is DynamicBody:
                    use_new_param_system = True
                    break
                # Also check if it's a source we recognize from new system
                if source in ('path', 'query', 'body', 'header', 'file', 'auto'):
                    use_new_param_system = True
                    break
        except Exception as e:
            logger.debug(f"ParamResolver.analyze_params failed, using legacy: {e}")
            use_new_param_system = False

        if use_new_param_system:
            # =================================================================
            # New Parameter System Path
            # =================================================================
            # Prepare data sources for ParamResolver

            # Build URL params dict from keys and values passed by decorator
            url_params_dict = {}
            if url_param_keys and url_param_values:
                for i, key in enumerate(url_param_keys):
                    if i < len(url_param_values):
                        url_params_dict[key] = url_param_values[i]
            # Fallback to params[0] if available
            if not url_params_dict and params[0]:
                url_params_dict = params[0]

            query_params_dict = params[1] if params[1] else {}
            body_params_dict = params[2] if params[2] else {}
            file_params_dict = params[3] if params[3] else {}

            # For new param system, also extract query params from request directly
            if not query_params_dict and hasattr(self, 'request'):
                # Extract all query arguments
                try:
                    for key in self.request.query_arguments:
                        values = self.request.query_arguments[key]
                        query_params_dict[key] = values[0].decode('utf-8') if values else None
                except Exception:
                    pass

            # If body_params is empty but request has body, try to parse it
            if not body_params_dict and hasattr(self, 'request') and self.request.body:
                try:
                    body_bytes = self.request.body
                    if isinstance(body_bytes, bytes):
                        body_bytes = body_bytes.decode('utf-8')
                    if body_bytes:
                        body_params_dict = json.loads(body_bytes)
                except Exception as e:
                    logger.debug(f"Failed to parse request body as JSON: {e}")
                    body_params_dict = {}

            # For new param system, extract headers from request directly
            headers_dict = {}
            if hasattr(self, 'request') and hasattr(self.request, 'headers'):
                try:
                    # Convert HTTPHeaders to dict
                    for key in self.request.headers:
                        headers_dict[key] = self.request.headers[key]
                except Exception:
                    pass
            # Merge with any headers from header_resolver (for backward compat)
            if headers:
                headers_dict.update(headers)

            # Resolve parameters using ParamResolver
            try:
                resolved_params = ParamResolver.resolve(
                    func=func,
                    request=self.request if hasattr(self, 'request') else None,
                    url_params=url_params_dict,
                    query_params=query_params_dict,
                    body_data=body_params_dict,
                    headers=headers_dict,
                    files=file_params_dict,
                )

                # Build param_list in correct order based on function signature
                sig = ParamResolver.get_signature(func)
                param_list = []
                for name, param in sig.parameters.items():
                    if name == 'self':
                        continue
                    if name in resolved_params:
                        param_list.append(resolved_params[name])
                    else:
                        param_list.append(None)

            except ResolveError as e:
                logger.warning(f"Parameter resolution failed: {e.message}, errors: {e.errors}")
                # Return error response
                self.set_status(400)
                self.write(json.dumps({
                    'error': 'Parameter validation failed',
                    'details': e.errors
                }))
                self.finish()
                return
        else:
            # =================================================================
            # Legacy Parameter System Path (backward compatibility)
            # =================================================================
            # Performance optimization: use pre-compiled parameter mapping
            param_names, needs_request_body, needs_headers = _get_cached_param_mapping(func)

            param_list = []
            for name in param_names:
                if name in KEY_NAME_INDEX:
                    idx = KEY_NAME_INDEX[name]
                    try:
                        param_list.append(params[idx])
                    except Exception:
                        param_list.append(None)
                elif name == 'request_body' and get_request_body:
                    param_list.append(self.request.body)
                elif name == 'headers' and headers is not None:
                    param_list.append(headers)
                else:
                    param_list.append(None)

        # Call the target function
        response_ret = func(controller_self, *param_list) if len(param_list) > 0 else func(controller_self)

        # [FIX CRITICAL] Detect and await async coroutines
        # If controller method is async def, func() returns a coroutine object
        # Must await to actually execute the async code
        # Use inspect.isawaitable to cover all awaitable objects (coroutine, generator-based coroutine, awaitable)
        if inspect.isawaitable(response_ret):
            response_ret = await response_ret

        # Return value takes priority, otherwise use the instance bound in context
        if response_ret is not None and hasattr(response_ret, "get_headers") and hasattr(response_ret, "get_status") and hasattr(response_ret, "get_body"):
            resp_obj = response_ret
        else:
            resp_obj = response.get()

        # Write out headers/status/body (using header registry)
        header_registry = get_header_registry()
        if header_registry.has_headers():
            for header in header_registry.get_headers():
                self.set_header(header[0], header[1])
        if resp_obj and getattr(resp_obj, "get_headers", None):
            for header in (resp_obj.get_headers() or []):
                self.set_header(header[0], header[1])
        if resp_obj:
            try:
                self.set_status(resp_obj.get_status())
            except Exception:
                self.set_status(200)
            try:
                self.write(resp_obj.get_body())
            except Exception:
                self.write(str(getattr(resp_obj, 'get_body', lambda: '')()))
        else:
            self.set_status(204)

        # Reset response instance for reuse (optimized with reset method)
        try:
            real_resp = response.get()
            if real_resp is not None and hasattr(real_resp, 'reset'):
                real_resp.reset()
        except Exception:
            pass

        self.finish()
    finally:
        # access log: method, uri, status, duration, client ip
        try:
            duration = time.time() - start_time
            try:
                status_code = self.get_status()
            except Exception:
                # fallback: if resp_obj is present, try to read status
                status_code = getattr(resp_obj, 'get_status', lambda: None)()
            # delegate to emit_access_log which supports different formats
            emit_access_log(self.request, resp_obj, status_code, duration)
        except Exception as e:
            # don't let logging failures break response cleanup
            logger.error('[ACCESS_LOG_ERROR] Failed to emit access log: %s', str(e), exc_info=True)
        # Return response to pool if pooling is enabled
        try:
            return_pooled_response(resp_instance)
        except Exception:
            pass
        # Must pop to avoid polluting the next request/scan
        response.pop(token)


def get_api(**kwargs: Any) -> Callable:
    def inner(func):
        url_param_key_list = []
        local_url = kwargs.get('url', '')
        original_url = local_url  # preserve original template for gateway Router
        if local_url.find("{") != -1:
            local_url, url_param_key_list = url_resolver(local_url)

        # Attach URL param keys and original template to function
        setattr(func, '__cullinan_url_param_keys__', url_param_key_list)
        setattr(func, '__cullinan_url__', original_url)
        setattr(func, '__cullinan_method__', 'get')

        @EncapsulationHandler.add_func(url=original_url, type='get')
        async def get(self, *args):
            # Conditional logging: only log if INFO level is enabled
            if logger.isEnabledFor(logging.INFO):
                logger.info("\t||| request:")
            # Simplified attribute access - use getattr with default
            caller_keys = tuple(getattr(self, 'get_controller_url_param_key_list', None) or url_param_key_list)
            url_values = tuple(args)
            query_params = kwargs.get('query_params') or ()
            file_params = kwargs.get('file_params') or []

            await request_handler(self,
                                  func,
                                  request_resolver(self, caller_keys + tuple(url_param_key_list),
                                                   url_values,
                                                   query_params, None,
                                                   file_params),
                                  header_resolver(self, kwargs.get('headers')),
                                  'get',
                                  url_param_keys=url_param_key_list,
                                  url_param_values=args)

        # Attach route metadata and original function reference for gateway dispatcher
        setattr(get, '__cullinan_url__', local_url)
        setattr(get, '__cullinan_method__', 'get')
        setattr(get, '__cullinan_original_func__', func)
        setattr(get, '__wrapped__', func)

        return get

    return inner


def post_api(**kwargs: Any) -> Callable:
    def inner(func):
        url_param_key_list = []
        local_url = kwargs.get('url', '')
        original_url = local_url
        if local_url.find("{") != -1:
            local_url, url_param_key_list = url_resolver(local_url)

        setattr(func, '__cullinan_url_param_keys__', url_param_key_list)
        setattr(func, '__cullinan_url__', original_url)
        setattr(func, '__cullinan_method__', 'post')

        @EncapsulationHandler.add_func(url=original_url, type='post')
        async def post(self, *args):
            # Conditional logging: only log if INFO level is enabled
            if logger.isEnabledFor(logging.INFO):
                logger.info("\t||| request:")
            # Simplified attribute access
            caller_keys = tuple(getattr(self, 'post_controller_url_param_key_list', None) or url_param_key_list)
            url_values = tuple(args)
            query_params = kwargs.get('query_params') or ()
            body_params = kwargs.get('body_params') or []
            file_params = kwargs.get('file_params') or []

            await request_handler(self,
                                  func,
                                  request_resolver(self, caller_keys + tuple(url_param_key_list),
                                                   url_values,
                                                   query_params,
                                                   body_params,
                                                   file_params),
                                  header_resolver(self, kwargs.get('headers')),
                                  'post',
                                  kwargs.get('get_request_body', False),
                                  url_param_keys=url_param_key_list,
                                  url_param_values=args)

        # Attach route metadata and original function reference for gateway dispatcher
        setattr(post, '__cullinan_url__', local_url)
        setattr(post, '__cullinan_method__', 'post')
        setattr(post, '__cullinan_original_func__', func)
        setattr(post, '__wrapped__', func)

        return post

    return inner


def patch_api(**kwargs: Any) -> Callable:
    def inner(func):
        url_param_key_list = []
        local_url = kwargs.get('url', '')
        original_url = local_url
        if local_url.find("{") != -1:
            local_url, url_param_key_list = url_resolver(local_url)

        setattr(func, '__cullinan_url_param_keys__', url_param_key_list)
        setattr(func, '__cullinan_url__', original_url)
        setattr(func, '__cullinan_method__', 'patch')

        @EncapsulationHandler.add_func(url=original_url, type='patch')
        async def patch(self, *args):
            # Conditional logging: only log if INFO level is enabled
            if logger.isEnabledFor(logging.INFO):
                logger.info("\t||| request:")
            # Simplified attribute access
            caller_keys = tuple(getattr(self, 'patch_controller_url_param_key_list', None) or url_param_key_list)
            url_values = tuple(args)
            query_params = kwargs.get('query_params') or ()
            body_params = kwargs.get('body_params') or []
            file_params = kwargs.get('file_params') or []

            await request_handler(self,
                                  func,
                                  request_resolver(self,
                                                   caller_keys + tuple(url_param_key_list), url_values,
                                                   query_params,
                                                   body_params, file_params),
                                  header_resolver(self, kwargs.get('headers')),
                                  'patch',
                                  kwargs.get('get_request_body', False),
                                  url_param_keys=url_param_key_list,
                                  url_param_values=args)

        # Attach route metadata and original function reference for gateway dispatcher
        setattr(patch, '__cullinan_url__', local_url)
        setattr(patch, '__cullinan_method__', 'patch')
        setattr(patch, '__cullinan_original_func__', func)
        setattr(patch, '__wrapped__', func)

        return patch

    return inner


def delete_api(**kwargs: Any) -> Callable:
    def inner(func):
        url_param_key_list = []
        local_url = kwargs.get('url', '')
        original_url = local_url
        if local_url.find("{") != -1:
            local_url, url_param_key_list = url_resolver(local_url)

        setattr(func, '__cullinan_url_param_keys__', url_param_key_list)
        setattr(func, '__cullinan_url__', original_url)
        setattr(func, '__cullinan_method__', 'delete')

        @EncapsulationHandler.add_func(url=original_url, type='delete')
        async def delete(self, *args):
            # Conditional logging: only log if INFO level is enabled
            if logger.isEnabledFor(logging.INFO):
                logger.info("\t||| request:")
            # Simplified attribute access
            caller_keys = tuple(getattr(self, 'delete_controller_url_param_key_list', None) or url_param_key_list)
            url_values = tuple(args)
            query_params = kwargs.get('query_params') or ()
            file_params = kwargs.get('file_params') or []

            await request_handler(self,
                                  func,
                                  request_resolver(self,
                                                   caller_keys + tuple(url_param_key_list), url_values,
                                                   query_params, None, file_params),
                                  header_resolver(self, kwargs.get('headers')),
                                  'delete',
                                  url_param_keys=url_param_key_list,
                                  url_param_values=args)

        # Attach route metadata and original function reference for gateway dispatcher
        setattr(delete, '__cullinan_url__', local_url)
        setattr(delete, '__cullinan_method__', 'delete')
        setattr(delete, '__cullinan_original_func__', func)
        setattr(delete, '__wrapped__', func)

        return delete

    return inner


def put_api(**kwargs: Any) -> Callable:
    def inner(func):
        url_param_key_list = []
        local_url = kwargs.get('url', '')
        original_url = local_url
        if local_url.find("{") != -1:
            local_url, url_param_key_list = url_resolver(local_url)

        setattr(func, '__cullinan_url_param_keys__', url_param_key_list)
        setattr(func, '__cullinan_url__', original_url)
        setattr(func, '__cullinan_method__', 'put')

        @EncapsulationHandler.add_func(url=original_url, type='put')
        async def put(self, *args):
            # Conditional logging: only log if INFO level is enabled
            if logger.isEnabledFor(logging.INFO):
                logger.info("\t||| request:")
            # Simplified attribute access
            caller_keys = tuple(getattr(self, 'put_controller_url_param_key_list', None) or url_param_key_list)
            url_values = tuple(args)
            query_params = kwargs.get('query_params') or ()
            file_params = kwargs.get('file_params') or []

            await request_handler(self,
                                  func,
                                  request_resolver(self,
                                                   caller_keys + tuple(url_param_key_list), url_values,
                                                   query_params, None, file_params),
                                  header_resolver(self, kwargs.get('headers')),
                                  'put',
                                  url_param_keys=url_param_key_list,
                                  url_param_values=args)

        # Attach route metadata and original function reference for gateway dispatcher
        setattr(put, '__cullinan_url__', local_url)
        setattr(put, '__cullinan_method__', 'put')
        setattr(put, '__cullinan_original_func__', func)
        setattr(put, '__wrapped__', func)

        return put

    return inner



class HttpResponse(object):
    """HTTP response object with memory optimization using __slots__.
    
    This class represents an HTTP response and uses __slots__ to reduce memory
    overhead by preventing dynamic attribute creation and avoiding the __dict__
    for each instance.
    
    Performance benefits:
        - 40-50% less memory per instance
        - Faster attribute access (direct offset vs dict lookup)
        - No runtime overhead
        
    Attributes:
        __body__: Response body content (str or bytes)
        __headers__: List of [name, value] header pairs
        __status__: HTTP status code (int)
        __status_msg__: Optional status message (str)
        __is_static__: Whether this is a static file response (bool)
    """
    __slots__ = ('__body__', '__headers__', '__status__', '__status_msg__', '__is_static__')
    
    # TYPE_LIST = {"JSON": "application/json", "ROW": "text/xml", "FORM": "application/x-www-form-urlencoded"}
    
    def __init__(self) -> None:
        self.__body__: str = ''
        self.__headers__: list = []
        self.__status__: int = 200
        self.__status_msg__: str = ''
        self.__is_static__: bool = False

    # __type__ = 'JSON'

    def set_status(self, status: int, msg: str = '') -> None:
        """Set the HTTP status code and optional message.
        
        Args:
            status: HTTP status code (e.g., 200, 404, 500)
            msg: Optional status message
        """
        self.__status__ = status
        self.__status_msg__ = msg

    def get_status(self) -> int:
        """Return the HTTP status code."""
        return self.__status__

    def set_body(self, data: Any) -> None:
        """Set the response body content.
        
        Args:
            data: Response body (typically str, bytes, or JSON-serializable object)
        """
        self.__body__ = data

    def add_header(self, name: str, value: str) -> None:
        """Add a header to the response.
        
        Args:
            name: Header name (e.g., 'Content-Type')
            value: Header value (e.g., 'application/json')
        """
        self.__headers__.append([name, value])

    def set_header(self, name: str, value: str) -> None:
        """Backward-compatible alias for add_header().

        Some user code calls resp.set_header(...). Internally we store headers
        as a list of [name, value] pairs, so set_header behaves like add_header.
        """
        self.add_header(name, value)

    def set_is_static(self, boolean: bool) -> None:
        """Mark whether this response is for a static file.
        
        Args:
            boolean: True if this is a static file response
        """
        self.__is_static__ = boolean

    def get_is_static(self) -> bool:
        """Return whether this is a static file response."""
        return self.__is_static__

    # def set_type(self, response_type):
    #     if response_type == self.TYPE_LIST["JSON"]:
    #         self.__type__ = response_type
    #     if response_type == self.TYPE_LIST["ROW"]:
    #         self.__type__ = response_type
    #     if response_type == self.TYPE_LIST["FORM"]:
    #         self.__type__ = response_type

    def get_body(self) -> Any:
        """Return the response body content."""
        return self.__body__

    def get_headers(self) -> list:
        """Return the list of response headers."""
        return self.__headers__

    def reset(self) -> None:
        """Reset the response object to default state for reuse.
        
        This method is optimized for object pooling scenarios where
        response objects are reused across multiple requests.
        """
        self.__body__ = ''
        self.__headers__ = []
        self.__status__ = 200
        self.__status_msg__ = ''
        self.__is_static__ = False

    # def get_type(self):
    #     return self.__type__

class StatusResponse(HttpResponse):
    """Status response with initialization from kwargs.
    
    This class extends HttpResponse to allow initialization with keyword arguments
    for status, headers, and body in a single constructor call.
    
    Example:
        resp = StatusResponse(
            status=404,
            status_msg="Not Found",
            headers=[["Content-Type", "application/json"]],
            body='{"error": "Resource not found"}'
        )
    """
    __slots__ = ()  # No additional slots needed, inherits from HttpResponse
    
    def __init__(self, **kwargs) -> None:
        """Initialize response with optional status, headers, and body.
        
        Args:
            status: HTTP status code (int, optional)
            status_msg: Status message (str, optional)
            headers: List of [name, value] header pairs (list, optional)
            body: Response body content (any, optional)
        """
        super().__init__()
        if kwargs.get("status", None) is not None and kwargs.get("status_msg", None) is not None:
            self.set_status(kwargs["status"], kwargs["status_msg"])
        if kwargs.get("headers", None) is not None:
            for key, value in kwargs["headers"]:
                self.add_header(key, value)
        if kwargs.get("body", None) is not None:
            self.set_body(kwargs["body"])


def response_build(**kwargs) -> StatusResponse:
    """Factory function to build a StatusResponse with the given parameters.
    
    Args:
        **kwargs: Keyword arguments passed to StatusResponse constructor
        
    Returns:
        A new StatusResponse instance
    """
    return StatusResponse(**kwargs)


# ============================================================================
# Response Object Pooling (Optional Performance Optimization)
# ============================================================================

from queue import Queue
from threading import Lock

class ResponsePool:
    """Thread-safe pool of HttpResponse objects for object reuse.
    
    This optimization reduces GC pressure and memory allocation overhead
    in high-concurrency scenarios by reusing response objects.
    
    Usage:
        response_pool = ResponsePool(size=100)
        resp = response_pool.acquire()
        # ... use response ...
        response_pool.release(resp)
    
    Note: This is an optional optimization that should be enabled via configuration.
    """
    
    def __init__(self, size: int = 100):
        """Initialize response pool with given size.
        
        Args:
            size: Maximum number of pooled response objects
        """
        self._pool = Queue(maxsize=size)
        self._lock = Lock()
        self._size = size
        
        # Pre-populate pool with response objects
        for _ in range(size):
            self._pool.put(HttpResponse())
    
    def acquire(self) -> HttpResponse:
        """Acquire a response object from the pool.
        
        Returns:
            HttpResponse object (new if pool is empty)
        """
        try:
            resp = self._pool.get_nowait()
            # Ensure it's reset
            if hasattr(resp, 'reset'):
                resp.reset()
            return resp
        except:
            # Pool empty, create new instance
            return HttpResponse()
    
    def release(self, resp: HttpResponse) -> None:
        """Release a response object back to the pool.
        
        Args:
            resp: HttpResponse object to return to pool
        """
        try:
            # Reset before returning to pool
            if hasattr(resp, 'reset'):
                resp.reset()
            self._pool.put_nowait(resp)
        except:
            # Pool full, let GC handle it
            pass
    
    def get_stats(self) -> dict:
        """Get pool statistics for monitoring.
        
        Returns:
            Dictionary with pool size and current availability
        """
        return {
            'size': self._size,
            'available': self._pool.qsize(),
            'in_use': self._size - self._pool.qsize()
        }


# Module-level pool instance (disabled by default)
_response_pool: Optional[ResponsePool] = None

def enable_response_pooling(pool_size: int = 100) -> None:
    """Enable response object pooling for performance optimization.
    
    This should be called during application initialization if object pooling
    is desired. It's particularly beneficial in high-concurrency scenarios.
    
    Args:
        pool_size: Size of the response pool (default: 100)
        
    Example:
        from cullinan.web.controller import enable_response_pooling
        enable_response_pooling(pool_size=200)
    """
    global _response_pool
    _response_pool = ResponsePool(size=pool_size)
    logger.info(f"Response object pooling enabled with size={pool_size}")


def disable_response_pooling() -> None:
    """Disable response object pooling.
    
    After calling this, new response objects will be created for each request.
    """
    global _response_pool
    _response_pool = None
    logger.info("Response object pooling disabled")


def get_pooled_response() -> HttpResponse:
    """Get a response from the pool if pooling is enabled.
    
    Returns:
        HttpResponse object (from pool if available, otherwise new instance)
    """
    if _response_pool is not None:
        return _response_pool.acquire()
    return HttpResponse()


def return_pooled_response(resp: HttpResponse) -> None:
    """Return a response to the pool if pooling is enabled.
    
    Args:
        resp: HttpResponse object to return to pool
    """
    if _response_pool is not None:
        _response_pool.release(resp)


def get_response_pool_stats() -> Optional[dict]:
    """Get response pool statistics if pooling is enabled.
    
    Returns:
        Dictionary with pool statistics, or None if pooling is disabled
    """
    if _response_pool is not None:
        return _response_pool.get_stats()
    return None
