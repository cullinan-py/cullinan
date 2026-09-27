# -*- coding: utf-8 -*-
"""Cullinan Router — High-Performance Route Matching

Implements a radix-tree (prefix tree) based router with support for:
- Static segments:    /api/users
- Parameter segments: /api/users/{id}
- Regex segments:     /api/files/{path:.*}
- Wildcard:           /static/**
- Per-method routing: GET /users  vs  POST /users

Author: plumeink
"""

import logging
import re
from typing import Any, Callable, Dict, List, Optional, Type, Tuple

from .route_types import RouteEntry, RouteMatch, HTTP_METHODS

logger = logging.getLogger(__name__)

# Default regex for a path parameter (no explicit pattern)
_DEFAULT_PARAM_RE = r'[^/]+'
# Regex to find {name} or {name:pattern} in a path template
_PARAM_PATTERN = re.compile(r'\{(\w+)(?::([^}]+))?}')


class _TrieNode:
    """Internal trie node used by Router.

    Each node represents a path segment (``users``, ``{id}``, etc.).
    """

    __slots__ = (
        'children',        # static children: segment_str -> _TrieNode
        'param_child',     # parameterised child (at most one per node)
        'param_name',      # name of the parameter if this IS a param node
        'param_regex',     # compiled regex for this parameter
        'wildcard_entry',  # catch-all route entry ( /** )
        'entries',         # method -> RouteEntry for this node (terminal)
    )

    def __init__(self) -> None:
        self.children: Dict[str, '_TrieNode'] = {}
        self.param_child: Optional['_TrieNode'] = None
        self.param_name: Optional[str] = None
        self.param_regex: Optional[re.Pattern] = None
        self.wildcard_entry: Optional[Dict[str, RouteEntry]] = None
        self.entries: Optional[Dict[str, RouteEntry]] = None


class Router:
    """High-performance prefix-tree router.

    Usage::

        router = Router()
        router.add_route('GET', '/api/users', handler=list_users)
        router.add_route('GET', '/api/users/{id}', handler=get_user)

        match = router.match('GET', '/api/users/42')
        # match.entry.handler -> get_user
        # match.path_params  -> {'id': '42'}
    """

    def __init__(
        self,
        case_sensitive: bool = True,
        trailing_slash: bool = False,
    ) -> None:
        """
        Args:
            case_sensitive: Whether route matching is case-sensitive.
            trailing_slash: If True, ``/foo`` and ``/foo/`` are treated as the same.
        """
        self._root: _TrieNode = _TrieNode()
        self._case_sensitive: bool = case_sensitive
        self._trailing_slash: bool = trailing_slash
        self._all_routes: List[RouteEntry] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def add_route(
        self,
        method: str,
        path: str,
        handler: Optional[Callable] = None,
        controller_cls: Optional[Type] = None,
        controller_method_name: str = '',
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RouteEntry:
        """Register a route.

        Args:
            method: HTTP method (e.g. ``'GET'``) or ``'*'`` for all methods.
            path: URL pattern (e.g. ``/api/users/{id}``).
            handler: The handler callable.
            controller_cls: Optional controller class.
            controller_method_name: Optional method name on the controller.
            metadata: Arbitrary metadata dict.

        Returns:
            The created ``RouteEntry``.

        Raises:
            ValueError: If path is invalid or conflicts with an existing route.
        """
        method = method.upper()
        if method != '*' and method not in HTTP_METHODS:
            raise ValueError(f'Unsupported HTTP method: {method}')

        # Normalise path
        path = self._normalise_path(path)

        # Parse parameter names & build segment list
        segments, param_names, path_regex = self._parse_path(path)

        entry = RouteEntry(
            method=method,
            path=path,
            path_regex=path_regex,
            handler=handler,
            controller_cls=controller_cls,
            controller_method_name=controller_method_name,
            param_names=tuple(param_names),
            metadata=metadata or {},
        )

        # Insert into trie
        node = self._root
        for seg in segments:
            if seg == '**':
                # Wildcard catch-all — store here and stop
                if node.wildcard_entry is None:
                    node.wildcard_entry = {}
                node.wildcard_entry[method] = entry
                self._all_routes.append(entry)
                logger.debug('Route registered: %s %s (wildcard)', method, path)
                return entry

            if seg.startswith('{') and seg.endswith('}'):
                # Parameter segment
                inner = seg[1:-1]
                pname, pregex = self._split_param(inner)
                if node.param_child is None:
                    node.param_child = _TrieNode()
                    node.param_child.param_name = pname
                    node.param_child.param_regex = re.compile(f'^{pregex}$') if pregex != _DEFAULT_PARAM_RE else None
                node = node.param_child
            else:
                # Static segment
                key = seg if self._case_sensitive else seg.lower()
                if key not in node.children:
                    node.children[key] = _TrieNode()
                node = node.children[key]

        # Terminal node — register entry by method
        if node.entries is None:
            node.entries = {}
        if method in node.entries:
            logger.warning('Route conflict: %s %s overwrites existing handler', method, path)
        node.entries[method] = entry
        self._all_routes.append(entry)

        logger.debug('Route registered: %s %s', method, path)
        return entry

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    def match(self, method: str, path: str) -> Optional[RouteMatch]:
        """Match a request to a registered route.

        Args:
            method: HTTP method (uppercase).
            path: Request path (e.g. ``/api/users/42``).

        Returns:
            A ``RouteMatch`` if found, else ``None``.
        """
        method = method.upper()
        path = self._normalise_path(path)
        segments = self._split_path(path)

        params: Dict[str, str] = {}
        result = self._match_node(self._root, segments, 0, method, params)
        return result

    def _match_node(
        self,
        node: _TrieNode,
        segments: List[str],
        idx: int,
        method: str,
        params: Dict[str, str],
    ) -> Optional[RouteMatch]:
        """Recursive trie walk."""
        if idx == len(segments):
            # Terminal — try exact method or wildcard method
            entry = self._get_entry(node, method)
            if entry:
                return RouteMatch(entry=entry, path_params=dict(params))
            return None

        seg = segments[idx]
        seg_key = seg if self._case_sensitive else seg.lower()

        # 1. Try static child
        static_child = node.children.get(seg_key)
        if static_child is not None:
            result = self._match_node(static_child, segments, idx + 1, method, params)
            if result is not None:
                return result

        # 2. Try parameter child
        if node.param_child is not None:
            pchild = node.param_child
            # validate regex if present
            if pchild.param_regex is None or pchild.param_regex.match(seg):
                old_val = params.get(pchild.param_name)
                params[pchild.param_name] = seg
                result = self._match_node(pchild, segments, idx + 1, method, params)
                if result is not None:
                    return result
                # backtrack
                if old_val is None:
                    params.pop(pchild.param_name, None)
                else:
                    params[pchild.param_name] = old_val

        # 3. Try wildcard
        if node.wildcard_entry is not None:
            entry = node.wildcard_entry.get(method) or node.wildcard_entry.get('*')
            if entry:
                # capture remaining path
                remaining = '/'.join(segments[idx:])
                params['_wildcard'] = remaining
                return RouteMatch(entry=entry, path_params=dict(params))

        return None

    @staticmethod
    def _get_entry(node: _TrieNode, method: str) -> Optional[RouteEntry]:
        if node.entries is None:
            return None
        entry = node.entries.get(method)
        if entry is None:
            entry = node.entries.get('*')
        return entry

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_all_routes(self) -> List[RouteEntry]:
        """Return all registered routes (for debugging / OpenAPI generation)."""
        return list(self._all_routes)

    def route_count(self) -> int:
        """Return total number of registered routes."""
        return len(self._all_routes)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _normalise_path(self, path: str) -> str:
        if not path.startswith('/'):
            path = '/' + path
        if self._trailing_slash and path != '/' and path.endswith('/'):
            path = path.rstrip('/')
        return path

    @staticmethod
    def _split_path(path: str) -> List[str]:
        """Split path into segments, ignoring empty parts."""
        return [s for s in path.split('/') if s]

    @staticmethod
    def _parse_path(path: str) -> Tuple[List[str], List[str], Optional[re.Pattern]]:
        """Parse a path template.

        Returns:
            (segments, param_names, compiled_regex_or_None)
        """
        raw_segments = [s for s in path.split('/') if s]
        param_names: List[str] = []
        regex_parts: List[str] = []
        has_params = False

        for seg in raw_segments:
            m = _PARAM_PATTERN.fullmatch(seg)
            if m:
                has_params = True
                pname = m.group(1)
                pregex = m.group(2) or _DEFAULT_PARAM_RE
                param_names.append(pname)
                regex_parts.append(f'(?P<{pname}>{pregex})')
            elif seg == '**':
                has_params = True
                regex_parts.append('(?P<_wildcard>.*)')
            else:
                regex_parts.append(re.escape(seg))

        compiled = None
        if has_params:
            full = '^/' + '/'.join(regex_parts) + '$'
            compiled = re.compile(full)

        return raw_segments, param_names, compiled

    @staticmethod
    def _split_param(inner: str) -> Tuple[str, str]:
        """Split ``name:pattern`` into ``(name, pattern)``."""
        if ':' in inner:
            name, pattern = inner.split(':', 1)
            return name, pattern
        return inner, _DEFAULT_PARAM_RE

