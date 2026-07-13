import logging

logging.getLogger("cullinan").addHandler(logging.NullHandler())

from cullinan._version import __version__ as _package_version
from cullinan.application import (
    CullinanConfig,
    application as _application_decorator,
    configure,
    get_config,
    module,
)
from cullinan.core.decorators import Inject, InjectByName, Lazy, component, service
from cullinan.core.injection_types import Provider
from cullinan.web import (
    Auto,
    AutoType,
    Body,
    BodyDecoderMiddleware,
    DynamicBody,
    File,
    Header,
    Middleware,
    Param,
    ParamResolver,
    ParamValidator,
    Path,
    Query,
    ResolveError,
    StaticFiles,
    TypeConverter,
    UNSET,
    ValidationError,
    WebRequest,
    WebResponse,
    controller,
    delete_api,
    get_api,
    get_decoded_body,
    get_missing_header_handler,
    middleware,
    patch_api,
    post_api,
    put_api,
    response,
    set_decoded_body,
    set_missing_header_handler,
    websocket_handler,
)


_REAL_APPLICATION_MODULE_NAME = "cullinan.application"

class _ApplicationFacade:
    """Top-level facade that stays callable while exposing / delegating
    to the real ``cullinan.application`` submodule.

    This facade exists because ``cullinan/__init__.py`` needs to expose
    ``application`` both as a callable (the decorator) AND as a namespace
    that looks like the submodule.  Simple attribute-access delegation
    is enough for reads; for writes (``mock.patch``, ``setattr``, …) we
    must forward to the real module so that consumers that imported
    names *from* the real module see the change.

    We resolve the real module via ``sys.modules`` (not a closure
    variable) because ``importlib.reload(cullinan)`` causes the closure
    ``_application_module`` to resolve to the *old* facade instance
    instead of ``sys.modules['cullinan.application']`` on Python < 3.12.
    """

    def __call__(self, *args, **kwargs):
        return _application_decorator(*args, **kwargs)

    # -- helpers -------------------------------------------------------

    @staticmethod
    def _get_real():
        """Return the real cullinan.application module, or None if it
        has been replaced by a non-module (e.g. a facade instance)."""
        import sys as _sys
        mod = _sys.modules.get(_REAL_APPLICATION_MODULE_NAME)
        if mod is not None and isinstance(mod, type(_sys)):
            return mod
        return None

    # -- read delegation ------------------------------------------------

    def __getattr__(self, name):
        if name == "__wrapped__":
            raise AttributeError(name)
        real = self._get_real()
        if real is None or real is self:
            raise AttributeError(name)
        return getattr(real, name)

    # -- write / delete delegation -------------------------------------

    def __setattr__(self, name, value):
        real = self._get_real()
        if real is None or real is self:
            return
        setattr(real, name, value)

    def __delattr__(self, name):
        real = self._get_real()
        if real is None or real is self:
            return
        delattr(real, name)


application = _ApplicationFacade()
__version__ = _package_version

__all__ = [
    "Auto",
    "AutoType",
    "Body",
    "BodyDecoderMiddleware",
    "CullinanConfig",
    "DynamicBody",
    "File",
    "Header",
    "Inject",
    "InjectByName",
    "Lazy",
    "Middleware",
    "Param",
    "ParamResolver",
    "ParamValidator",
    "Path",
    "Provider",
    "Query",
    "ResolveError",
    "StaticFiles",
    "TypeConverter",
    "UNSET",
    "ValidationError",
    "WebRequest",
    "WebResponse",
    "application",
    "component",
    "configure",
    "controller",
    "delete_api",
    "get_api",
    "get_config",
    "get_decoded_body",
    "get_missing_header_handler",
    "middleware",
    "module",
    "patch_api",
    "post_api",
    "put_api",
    "response",
    "service",
    "set_decoded_body",
    "set_missing_header_handler",
    "websocket_handler",
]
