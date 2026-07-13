# -*- coding: utf-8 -*-
"""Cullinan ModelResolver Tests

Tests dataclass model resolution.

Author: Cullinan
"""

import unittest
from dataclasses import dataclass
from typing import Optional, List

from cullinan.web.params import (
    ModelResolver,
    ModelError,
)


@dataclass
class SimpleUser:
    name: str
    age: int


@dataclass
class UserWithDefaults:
    name: str
    age: int = 0
    email: str = ""


@dataclass
class UserWithOptional:
    name: str
    nickname: Optional[str] = None


@dataclass
class Address:
    city: str
    street: str


@dataclass
class UserWithAddress:
    name: str
    address: Address


class TestModelResolverBasic(unittest.TestCase):
    """Test basic model resolution"""

    def test_is_dataclass(self):
        """Detect dataclass"""
        self.assertTrue(ModelResolver.is_dataclass(SimpleUser))
        self.assertFalse(ModelResolver.is_dataclass(str))
        self.assertFalse(ModelResolver.is_dataclass(dict))

    def test_resolve_simple(self):
        """Resolve simple model"""
        data = {'name': 'test', 'age': 25}
        user = ModelResolver.resolve(SimpleUser, data)
        self.assertEqual(user.name, 'test')
        self.assertEqual(user.age, 25)

    def test_resolve_with_type_conversion(self):
        """Type conversion during resolution"""
        data = {'name': 'test', 'age': '30'}  # age is a string
        user = ModelResolver.resolve(SimpleUser, data)
        self.assertEqual(user.age, 30)

    def test_resolve_missing_required(self):
        """Missing required field"""
        data = {'name': 'test'}  # missing age
        with self.assertRaises(ModelError) as ctx:
            ModelResolver.resolve(SimpleUser, data)
        self.assertTrue(len(ctx.exception.field_errors) > 0)

    def test_resolve_with_defaults(self):
        """Use default values"""
        data = {'name': 'test'}
        user = ModelResolver.resolve(UserWithDefaults, data)
        self.assertEqual(user.name, 'test')
        self.assertEqual(user.age, 0)
        self.assertEqual(user.email, '')

    def test_resolve_override_defaults(self):
        """Override default values"""
        data = {'name': 'test', 'age': 18, 'email': 'test@example.com'}
        user = ModelResolver.resolve(UserWithDefaults, data)
        self.assertEqual(user.age, 18)
        self.assertEqual(user.email, 'test@example.com')


class TestModelResolverOptional(unittest.TestCase):
    """Test Optional type"""

    def test_optional_with_value(self):
        """Optional with value"""
        data = {'name': 'test', 'nickname': 'nick'}
        user = ModelResolver.resolve(UserWithOptional, data)
        self.assertEqual(user.nickname, 'nick')

    def test_optional_without_value(self):
        """Optional without value"""
        data = {'name': 'test'}
        user = ModelResolver.resolve(UserWithOptional, data)
        self.assertIsNone(user.nickname)

    def test_optional_with_none(self):
        """Optional with explicit None"""
        data = {'name': 'test', 'nickname': None}
        user = ModelResolver.resolve(UserWithOptional, data)
        self.assertIsNone(user.nickname)


class TestModelResolverNested(unittest.TestCase):
    """Test nested dataclass"""

    def test_nested_resolve(self):
        """Resolve nested model"""
        data = {
            'name': 'test',
            'address': {
                'city': 'Beijing',
                'street': 'Main Street'
            }
        }
        user = ModelResolver.resolve(UserWithAddress, data)
        self.assertEqual(user.name, 'test')
        self.assertEqual(user.address.city, 'Beijing')
        self.assertEqual(user.address.street, 'Main Street')

    def test_nested_missing_required(self):
        """Nested model missing field"""
        data = {
            'name': 'test',
            'address': {'city': 'Beijing'}  # missing street
        }
        with self.assertRaises(ModelError):
            ModelResolver.resolve(UserWithAddress, data)


class TestModelResolverToDict(unittest.TestCase):
    """Test to_dict"""

    def test_simple_to_dict(self):
        """Simple model to dict"""
        user = SimpleUser(name='test', age=25)
        data = ModelResolver.to_dict(user)
        self.assertEqual(data, {'name': 'test', 'age': 25})

    def test_nested_to_dict(self):
        """Nested model to dict"""
        address = Address(city='Beijing', street='Main Street')
        user = UserWithAddress(name='test', address=address)
        data = ModelResolver.to_dict(user)
        self.assertEqual(data['name'], 'test')
        self.assertEqual(data['address']['city'], 'Beijing')


class TestModelResolverErrors(unittest.TestCase):
    """Test error handling"""

    def test_not_dataclass(self):
        """Non-dataclass type"""
        with self.assertRaises(ModelError):
            ModelResolver.resolve(dict, {})

    def test_error_to_dict(self):
        """Error to dict"""
        try:
            ModelResolver.resolve(SimpleUser, {'name': 'test'})
        except ModelError as e:
            d = e.to_dict()
            self.assertIn('message', d)
            self.assertIn('field_errors', d)

