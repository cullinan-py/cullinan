# -*- coding: utf-8 -*-
"""Cullinan Params Module Tests

Tests parameter marker classes.

Author: Cullinan
"""

import unittest

from cullinan.web.params import (
    Param,
    Path,
    Query,
    Body,
    Header,
    File,
    UNSET,
)


class TestUNSET(unittest.TestCase):
    """Test UNSET sentinel"""

    def test_singleton(self):
        """UNSET should be a singleton"""
        from cullinan.web.params.base import _UNSET
        a = _UNSET()
        b = _UNSET()
        self.assertIs(a, b)
        self.assertIs(a, UNSET)

    def test_bool_is_false(self):
        """UNSET boolean value should be False"""
        self.assertFalse(UNSET)
        self.assertFalse(bool(UNSET))

    def test_repr(self):
        """UNSET string representation"""
        self.assertEqual(repr(UNSET), '<UNSET>')


class TestParam(unittest.TestCase):
    """Test Param base class"""

    def test_default_values(self):
        """Default values test"""
        p = Param()
        self.assertEqual(p.type_, str)
        self.assertTrue(p.required)
        self.assertIs(p.default, UNSET)
        self.assertIsNone(p.name)

    def test_with_type(self):
        """Specify type"""
        p = Param(int)
        self.assertEqual(p.type_, int)

    def test_with_default_sets_required_false(self):
        """required is automatically False when default is set"""
        p = Param(str, default='test')
        self.assertFalse(p.required)
        self.assertEqual(p.default, 'test')

    def test_explicit_required_with_default(self):
        """When required=True explicitly but has default, required is still False"""
        p = Param(str, required=True, default='test')
        self.assertFalse(p.required)

    def test_validators(self):
        """Validators construction"""
        p = Param(int, ge=0, le=100, min_length=1)
        validators = p.get_validators()
        self.assertEqual(len(validators), 3)
        self.assertIn(('ge', 0), validators)
        self.assertIn(('le', 100), validators)
        self.assertIn(('min_length', 1), validators)

    def test_has_default(self):
        """has_default method"""
        p1 = Param()
        p2 = Param(default='test')
        self.assertFalse(p1.has_default())
        self.assertTrue(p2.has_default())

    def test_get_default(self):
        """get_default method"""
        p1 = Param()
        p2 = Param(default='test')
        self.assertIsNone(p1.get_default())
        self.assertEqual(p2.get_default(), 'test')

    def test_repr(self):
        """String representation"""
        p = Param(int, name='age', default=0)
        repr_str = repr(p)
        self.assertIn('Param', repr_str)
        self.assertIn('int', repr_str)
        self.assertIn('age', repr_str)


class TestPath(unittest.TestCase):
    """Test Path parameter type"""

    def test_source(self):
        """Source identifier"""
        p = Path(int)
        self.assertEqual(p.source, 'path')

    def test_always_required(self):
        """Path parameter is always required"""
        p = Path(int)
        self.assertTrue(p.required)

    def test_no_default(self):
        """Path parameter does not support default values"""
        p = Path(int)
        self.assertIs(p.default, UNSET)

    def test_with_validators(self):
        """With validators"""
        p = Path(int, ge=1)
        validators = p.get_validators()
        self.assertIn(('ge', 1), validators)


class TestQuery(unittest.TestCase):
    """Test Query parameter type"""

    def test_source(self):
        """Source identifier"""
        p = Query(str)
        self.assertEqual(p.source, 'query')

    def test_with_default(self):
        """With default value"""
        p = Query(int, default=1)
        self.assertFalse(p.required)
        self.assertEqual(p.default, 1)

    def test_optional(self):
        """Optional parameter"""
        p = Query(str, required=False)
        self.assertFalse(p.required)


class TestBody(unittest.TestCase):
    """Test Body parameter type"""

    def test_source(self):
        """Source identifier"""
        p = Body(str)
        self.assertEqual(p.source, 'body')

    def test_with_validators(self):
        """With validators"""
        p = Body(int, ge=0, le=100)
        validators = p.get_validators()
        self.assertIn(('ge', 0), validators)
        self.assertIn(('le', 100), validators)


class TestHeader(unittest.TestCase):
    """Test Header parameter type"""

    def test_source(self):
        """Source identifier"""
        p = Header(str)
        self.assertEqual(p.source, 'header')

    def test_with_alias(self):
        """With alias"""
        p = Header(str, alias='Authorization')
        self.assertEqual(p.alias, 'Authorization')

    def test_optional_with_default(self):
        """Optional with default value"""
        p = Header(str, default='Bearer token')
        self.assertFalse(p.required)
        self.assertEqual(p.default, 'Bearer token')


class TestFile(unittest.TestCase):
    """Test File parameter type"""

    def test_source(self):
        """Source identifier"""
        p = File()
        self.assertEqual(p.source, 'file')

    def test_type_is_bytes(self):
        """File type is bytes"""
        p = File()
        self.assertEqual(p.type_, bytes)

    def test_max_size(self):
        """Maximum file size"""
        p = File(max_size=1024)
        self.assertEqual(p.max_size, 1024)

    def test_allowed_types(self):
        """Allowed MIME types"""
        p = File(allowed_types=['image/png', 'image/jpeg'])
        self.assertEqual(p.allowed_types, ['image/png', 'image/jpeg'])

    def test_repr(self):
        """String representation"""
        p = File(name='avatar', max_size=1024)
        repr_str = repr(p)
        self.assertIn('File', repr_str)
        self.assertIn('avatar', repr_str)

