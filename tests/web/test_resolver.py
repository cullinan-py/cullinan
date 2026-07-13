# -*- coding: utf-8 -*-
"""Cullinan ParamResolver Tests

Tests parameter resolution orchestrator.

Author: Cullinan
"""

import unittest
from dataclasses import dataclass
from typing import Optional

from cullinan.web.params import (
    ParamResolver,
    ResolveError,
    Path,
    Query,
    Body,
    Header,
    DynamicBody,
    AutoType,
)


# Mock functions for testing

def func_with_path_params(self, user_id: Path(int), name: Path(str)):
    pass


def func_with_query_params(self, page: Query(int, default=1), size: Query(int, default=10, ge=1, le=100)):
    pass


def func_with_body_params(self, name: Body(str), age: Body(int, default=0)):
    pass


def func_with_header_params(self, auth: Header(str, alias='Authorization')):
    pass


def func_with_dynamic_body(self, body: DynamicBody):
    pass


@dataclass
class CreateUserRequest:
    name: str
    age: int = 0


def func_with_dataclass(self, user: CreateUserRequest):
    pass


def func_with_auto_type(self, value: AutoType):
    pass


def func_with_mixed_params(
    self,
    user_id: Path(int),
    page: Query(int, default=1),
    name: Body(str),
):
    pass


class TestParamResolverAnalyze(unittest.TestCase):
    """Test parameter analysis"""

    def test_analyze_path_params(self):
        """Analyze path parameters"""
        config = ParamResolver.analyze_params(func_with_path_params)
        self.assertIn('user_id', config)
        self.assertEqual(config['user_id']['source'], 'path')
        self.assertEqual(config['user_id']['type'], int)

    def test_analyze_query_params(self):
        """Analyze query parameters"""
        config = ParamResolver.analyze_params(func_with_query_params)
        self.assertIn('page', config)
        self.assertEqual(config['page']['source'], 'query')
        self.assertEqual(config['page']['default'], 1)

    def test_analyze_body_params(self):
        """Analyze body parameters"""
        config = ParamResolver.analyze_params(func_with_body_params)
        self.assertIn('name', config)
        self.assertEqual(config['name']['source'], 'body')

    def test_analyze_dynamic_body(self):
        """Analyze DynamicBody"""
        config = ParamResolver.analyze_params(func_with_dynamic_body)
        self.assertIn('body', config)
        self.assertEqual(config['body']['type'], DynamicBody)

    def test_analyze_dataclass(self):
        """Analyze dataclass"""
        config = ParamResolver.analyze_params(func_with_dataclass)
        self.assertIn('user', config)
        self.assertEqual(config['user']['type'], CreateUserRequest)


class TestParamResolverResolve(unittest.TestCase):
    """Test parameter resolution"""

    def test_resolve_path_params(self):
        """Resolve path parameters"""
        result = ParamResolver.resolve(
            func_with_path_params,
            request=None,
            url_params={'user_id': '123', 'name': 'test'}
        )
        self.assertEqual(result['user_id'], 123)
        self.assertEqual(result['name'], 'test')

    def test_resolve_query_params(self):
        """Resolve query parameters"""
        result = ParamResolver.resolve(
            func_with_query_params,
            request=None,
            query_params={'page': '2', 'size': '20'}
        )
        self.assertEqual(result['page'], 2)
        self.assertEqual(result['size'], 20)

    def test_resolve_query_defaults(self):
        """Resolve query parameter defaults"""
        result = ParamResolver.resolve(
            func_with_query_params,
            request=None,
            query_params={}
        )
        self.assertEqual(result['page'], 1)
        self.assertEqual(result['size'], 10)

    def test_resolve_body_params(self):
        """Resolve body parameters"""
        result = ParamResolver.resolve(
            func_with_body_params,
            request=None,
            body_data={'name': 'test', 'age': '25'}
        )
        self.assertEqual(result['name'], 'test')
        self.assertEqual(result['age'], 25)

    def test_resolve_dynamic_body(self):
        """Resolve DynamicBody"""
        result = ParamResolver.resolve(
            func_with_dynamic_body,
            request=None,
            body_data={'name': 'test', 'age': 25}
        )
        self.assertIsInstance(result['body'], DynamicBody)
        self.assertEqual(result['body'].name, 'test')

    def test_resolve_dataclass(self):
        """Resolve dataclass"""
        result = ParamResolver.resolve(
            func_with_dataclass,
            request=None,
            body_data={'name': 'test', 'age': '30'}
        )
        self.assertIsInstance(result['user'], CreateUserRequest)
        self.assertEqual(result['user'].name, 'test')
        self.assertEqual(result['user'].age, 30)

    def test_resolve_auto_type(self):
        """Resolve AutoType"""
        result = ParamResolver.resolve(
            func_with_auto_type,
            request=None,
            query_params={'value': '123'}
        )
        self.assertEqual(result['value'], 123)

        result = ParamResolver.resolve(
            func_with_auto_type,
            request=None,
            query_params={'value': 'true'}
        )
        self.assertEqual(result['value'], True)

    def test_resolve_mixed_params(self):
        """Resolve mixed parameters"""
        result = ParamResolver.resolve(
            func_with_mixed_params,
            request=None,
            url_params={'user_id': '123'},
            query_params={'page': '2'},
            body_data={'name': 'test'}
        )
        self.assertEqual(result['user_id'], 123)
        self.assertEqual(result['page'], 2)
        self.assertEqual(result['name'], 'test')


class TestParamResolverValidation(unittest.TestCase):
    """Test parameter validation"""

    def test_validation_ge(self):
        """Validate ge constraint"""
        # Normal value
        result = ParamResolver.resolve(
            func_with_query_params,
            request=None,
            query_params={'page': '1', 'size': '50'}
        )
        self.assertEqual(result['size'], 50)

        # Out of range
        with self.assertRaises(ResolveError):
            ParamResolver.resolve(
                func_with_query_params,
                request=None,
                query_params={'page': '1', 'size': '200'}  # > 100
            )

    def test_missing_required(self):
        """Missing required parameter"""
        with self.assertRaises(ResolveError):
            ParamResolver.resolve(
                func_with_body_params,
                request=None,
                body_data={}  # missing name
            )


class TestParamResolverAlias(unittest.TestCase):
    """Test alias"""

    def test_header_alias(self):
        """Header alias"""
        result = ParamResolver.resolve(
            func_with_header_params,
            request=None,
            headers={'Authorization': 'Bearer token'}
        )
        self.assertEqual(result['auth'], 'Bearer token')


class TestParamResolverError(unittest.TestCase):
    """Test error handling"""

    def test_error_to_dict(self):
        """Error to dict"""
        try:
            ParamResolver.resolve(
                func_with_body_params,
                request=None,
                body_data={}
            )
        except ResolveError as e:
            d = e.to_dict()
            self.assertIn('message', d)
            self.assertIn('errors', d)
            self.assertTrue(len(d['errors']) > 0)


class TestParamResolverCache(unittest.TestCase):
    """Test cache"""

    def test_signature_cache(self):
        """Signature cache"""
        # First call
        sig1 = ParamResolver.get_signature(func_with_path_params)
        # Second call should return the same object
        sig2 = ParamResolver.get_signature(func_with_path_params)
        self.assertIs(sig1, sig2)

    def test_clear_cache(self):
        """Clear cache"""
        ParamResolver.get_signature(func_with_path_params)
        self.assertIn(func_with_path_params, ParamResolver._signature_cache)
        ParamResolver.clear_cache()
        self.assertNotIn(func_with_path_params, ParamResolver._signature_cache)

