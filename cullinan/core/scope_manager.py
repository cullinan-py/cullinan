# -*- coding: utf-8 -*-
"""Unified scope management for Cullinan."""

from __future__ import annotations

import threading
from contextvars import ContextVar
from typing import Any, Callable, Dict, Optional

from cullinan.support.diagnostics import unknown_scope_type

from .definitions import ScopeType
from .exceptions import ContainerDrainingError, ScopeNotActiveError

_current_request_scope: ContextVar[Optional["RequestScope"]] = ContextVar(
    "cullinan_request_scope", default=None
)


class SingletonScope:
    __slots__ = ("_instances", "_lock")

    def __init__(self):
        self._instances: Dict[str, Any] = {}
        self._lock = threading.RLock()

    def get(self, name: str, factory: Callable[[], Any]) -> Any:
        if name in self._instances:
            return self._instances[name]
        with self._lock:
            if name not in self._instances:
                self._instances[name] = factory()
            return self._instances[name]

    def has(self, name: str) -> bool:
        return name in self._instances

    def clear(self) -> None:
        with self._lock:
            self._instances.clear()


class PrototypeScope:
    __slots__ = ()

    def get(self, name: str, factory: Callable[[], Any]) -> Any:
        return factory()

    @staticmethod
    def has(name: str) -> bool:
        return False

    @staticmethod
    def clear() -> None:
        return None


class RequestScope:
    __slots__ = ("root_id", "_instances", "_closed")

    def __init__(self, root_id: str):
        self.root_id = root_id
        self._instances: Dict[str, Any] = {}
        self._closed = False

    def get(self, name: str, factory: Callable[[], Any]) -> Any:
        if self._closed:
            raise ScopeNotActiveError(
                scope_type="REQUEST",
                dependency_name=name,
                message=f"Request scope is closed, so '{name}' cannot be resolved.",
            )
        if name not in self._instances:
            self._instances[name] = factory()
        return self._instances[name]

    def has(self, name: str) -> bool:
        return name in self._instances

    def close(self) -> None:
        self._instances.clear()
        self._closed = True

    @property
    def instances(self) -> Dict[str, Any]:
        return self._instances


class ScopeManager:
    __slots__ = (
        "_root_id",
        "_singleton",
        "_prototype",
        "_lock",
        "_active_request_count",
        "_accepting_requests",
    )

    def __init__(self, root_id: str):
        self._root_id = root_id
        self._singleton = SingletonScope()
        self._prototype = PrototypeScope()
        self._lock = threading.RLock()
        self._active_request_count = 0
        self._accepting_requests = True

    @property
    def root_id(self) -> str:
        return self._root_id

    def get(self, scope_type: ScopeType, name: str, factory: Callable[[], Any]) -> Any:
        if scope_type == ScopeType.SINGLETON:
            return self._singleton.get(name, factory)
        if scope_type == ScopeType.PROTOTYPE:
            return self._prototype.get(name, factory)
        if scope_type == ScopeType.REQUEST:
            scope = _current_request_scope.get()
            if scope is None or scope.root_id != self._root_id:
                raise ScopeNotActiveError(
                    scope_type="REQUEST",
                    dependency_name=name,
                    message=(
                        f"Cannot resolve request-scoped dependency '{name}': "
                        "there is no active request context for this root container."
                    ),
                )
            return scope.get(name, factory)
        raise ValueError(unknown_scope_type(scope_type))

    def has(self, scope_type: ScopeType, name: str) -> bool:
        if scope_type == ScopeType.SINGLETON:
            return self._singleton.has(name)
        if scope_type == ScopeType.PROTOTYPE:
            return self._prototype.has(name)
        if scope_type == ScopeType.REQUEST:
            scope = _current_request_scope.get()
            return scope is not None and scope.root_id == self._root_id and scope.has(name)
        return False

    def clear_all(self) -> None:
        self._singleton.clear()
        scope = _current_request_scope.get()
        if scope is not None and scope.root_id == self._root_id:
            scope.close()
            _current_request_scope.set(None)

    def enter_request_context(self):
        with self._lock:
            if not self._accepting_requests:
                raise ContainerDrainingError(
                    "The current root container is draining and cannot accept new request scopes."
                )
            self._active_request_count += 1
        scope = RequestScope(self._root_id)
        _current_request_scope.set(scope)
        return scope.instances

    def exit_request_context(self) -> None:
        scope = _current_request_scope.get()
        if scope is None or scope.root_id != self._root_id:
            return
        scope.close()
        _current_request_scope.set(None)
        with self._lock:
            if self._active_request_count > 0:
                self._active_request_count -= 1

    def is_request_active(self) -> bool:
        scope = _current_request_scope.get()
        return scope is not None and scope.root_id == self._root_id

    def begin_drain(self) -> None:
        with self._lock:
            self._accepting_requests = False

    @property
    def active_request_count(self) -> int:
        with self._lock:
            return self._active_request_count


__all__ = [
    "ScopeType",
    "SingletonScope",
    "PrototypeScope",
    "RequestScope",
    "ScopeManager",
]
