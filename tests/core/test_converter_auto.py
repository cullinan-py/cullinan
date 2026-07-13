# -*- coding: utf-8 -*-
"""Cullinan TypeConverter and Auto Tests

Testing type conversion and automatic type inference.

Author: Cullinan
"""

import unittest

from cullinan.web.params import (
    TypeConverter,
    ConversionError,
    Auto,
    AutoType,
    DynamicBody,
)


class TestTypeConverter(unittest.TestCase):
    """Test TypeConverter"""

    def test_convert_to_str(self):
        """Convert to string"""
        self.assertEqual(TypeConverter.convert(123, str), "123")
        self.assertEqual(TypeConverter.convert(True, str), "True")
        self.assertEqual(TypeConverter.convert(b"hello", str), "hello")

    def test_convert_to_int(self):
        """Convert to integer"""
        self.assertEqual(TypeConverter.convert("123", int), 123)
        self.assertEqual(TypeConverter.convert("12.5", int), 12)
        self.assertEqual(TypeConverter.convert(12.9, int), 12)
        self.assertEqual(TypeConverter.convert(True, int), 1)
        self.assertEqual(TypeConverter.convert(False, int), 0)

    def test_convert_to_int_error(self):
        """Integer conversion error"""
        with self.assertRaises(ConversionError):
            TypeConverter.convert("", int)
        with self.assertRaises(ConversionError):
            TypeConverter.convert("abc", int)

    def test_convert_to_float(self):
        """Convert to float"""
        self.assertEqual(TypeConverter.convert("12.5", float), 12.5)
        self.assertEqual(TypeConverter.convert("123", float), 123.0)
        self.assertEqual(TypeConverter.convert(123, float), 123.0)

    def test_convert_to_float_error(self):
        """Float conversion error"""
        with self.assertRaises(ConversionError):
            TypeConverter.convert("", float)

    def test_convert_to_bool(self):
        """Convert to boolean"""
        # Truthy values
        self.assertTrue(TypeConverter.convert("true", bool))
        self.assertTrue(TypeConverter.convert("True", bool))
        self.assertTrue(TypeConverter.convert("1", bool))
        self.assertTrue(TypeConverter.convert("yes", bool))
        self.assertTrue(TypeConverter.convert("on", bool))

        # Falsy values
        self.assertFalse(TypeConverter.convert("false", bool))
        self.assertFalse(TypeConverter.convert("False", bool))
        self.assertFalse(TypeConverter.convert("0", bool))
        self.assertFalse(TypeConverter.convert("no", bool))
        self.assertFalse(TypeConverter.convert("off", bool))
        self.assertFalse(TypeConverter.convert("", bool))

    def test_convert_to_bool_error(self):
        """Boolean conversion error"""
        with self.assertRaises(ConversionError):
            TypeConverter.convert("maybe", bool)

    def test_convert_to_list(self):
        """Convert to list"""
        self.assertEqual(TypeConverter.convert("a,b,c", list), ["a", "b", "c"])
        self.assertEqual(TypeConverter.convert("[1,2,3]", list), [1, 2, 3])
        self.assertEqual(TypeConverter.convert((1, 2), list), [1, 2])
        self.assertEqual(TypeConverter.convert("single", list), ["single"])
        self.assertEqual(TypeConverter.convert("", list), [])

    def test_convert_to_dict(self):
        """Convert to dict"""
        self.assertEqual(TypeConverter.convert('{"a": 1}', dict), {"a": 1})
        self.assertEqual(TypeConverter.convert({"a": 1}, dict), {"a": 1})

    def test_convert_to_dict_error(self):
        """Dict conversion error"""
        with self.assertRaises(ConversionError):
            TypeConverter.convert("not json", dict)

    def test_convert_to_bytes(self):
        """Convert to bytes"""
        self.assertEqual(TypeConverter.convert("hello", bytes), b"hello")
        self.assertEqual(TypeConverter.convert(b"hello", bytes), b"hello")

    def test_convert_none(self):
        """None value handling"""
        self.assertIsNone(TypeConverter.convert(None, str))
        self.assertIsNone(TypeConverter.convert(None, int))

    def test_convert_same_type(self):
        """Same type returned directly"""
        self.assertEqual(TypeConverter.convert("test", str), "test")
        self.assertEqual(TypeConverter.convert(123, int), 123)

    def test_can_convert(self):
        """can_convert method"""
        self.assertTrue(TypeConverter.can_convert("123", int))
        self.assertFalse(TypeConverter.can_convert("abc", int))


class TestAuto(unittest.TestCase):
    """Test automatic type inference"""

    def test_infer_none(self):
        """Infer None"""
        self.assertIsNone(Auto.infer(None))
        self.assertIsNone(Auto.infer("null"))
        self.assertIsNone(Auto.infer("None"))

    def test_infer_bool(self):
        """Infer boolean"""
        self.assertTrue(Auto.infer("true"))
        self.assertTrue(Auto.infer("True"))
        self.assertTrue(Auto.infer("yes"))
        self.assertFalse(Auto.infer("false"))
        self.assertFalse(Auto.infer("no"))

    def test_infer_int(self):
        """Infer integer"""
        self.assertEqual(Auto.infer("123"), 123)
        self.assertEqual(Auto.infer("-456"), -456)
        self.assertEqual(Auto.infer("0"), 0)

    def test_infer_float(self):
        """Infer float"""
        self.assertEqual(Auto.infer("12.5"), 12.5)
        self.assertEqual(Auto.infer("-3.14"), -3.14)
        self.assertEqual(Auto.infer("1e10"), 1e10)

    def test_infer_dict(self):
        """Infer dict"""
        result = Auto.infer('{"name": "test"}')
        self.assertEqual(result, {"name": "test"})

    def test_infer_list(self):
        """Infer list"""
        result = Auto.infer('[1, 2, 3]')
        self.assertEqual(result, [1, 2, 3])

    def test_infer_string(self):
        """Keep string"""
        self.assertEqual(Auto.infer("hello"), "hello")
        self.assertEqual(Auto.infer(""), "")

    def test_infer_non_string(self):
        """Non-string returned directly"""
        self.assertEqual(Auto.infer(123), 123)
        self.assertEqual(Auto.infer([1, 2]), [1, 2])

    def test_infer_type(self):
        """Infer type"""
        self.assertEqual(Auto.infer_type("123"), int)
        self.assertEqual(Auto.infer_type("12.5"), float)
        self.assertEqual(Auto.infer_type("true"), bool)
        self.assertEqual(Auto.infer_type("hello"), str)
        self.assertEqual(Auto.infer_type('{"a":1}'), dict)
        self.assertEqual(Auto.infer_type('[1,2]'), list)


class TestAutoType(unittest.TestCase):
    """Test AutoType marker"""

    def test_is_class(self):
        """AutoType is a class"""
        self.assertTrue(isinstance(AutoType, type))


class TestDynamicBody(unittest.TestCase):
    """Test dynamic request body"""

    def setUp(self):
        self.body = DynamicBody({
            'name': 'test',
            'age': 18,
            'user': {'id': 1, 'role': 'admin'}
        })

    def test_attribute_access(self):
        """Attribute access"""
        self.assertEqual(self.body.name, 'test')
        self.assertEqual(self.body.age, 18)

    def test_nested_access(self):
        """Nested access"""
        self.assertEqual(self.body.user.id, 1)
        self.assertEqual(self.body.user.role, 'admin')

    def test_attribute_not_found(self):
        """Attribute not found"""
        with self.assertRaises(AttributeError):
            _ = self.body.email

    def test_get_method(self):
        """get method"""
        self.assertEqual(self.body.get('name'), 'test')
        self.assertEqual(self.body.get('email', 'default'), 'default')

    def test_dict_access(self):
        """Dict-style access"""
        self.assertEqual(self.body['name'], 'test')

    def test_contains(self):
        """Contains check"""
        self.assertTrue('name' in self.body)
        self.assertFalse('email' in self.body)

    def test_set_attribute(self):
        """Set attribute"""
        self.body.email = 'test@example.com'
        self.assertEqual(self.body.email, 'test@example.com')

    def test_delete_attribute(self):
        """Delete attribute"""
        self.body.temp = 'value'
        del self.body.temp
        self.assertFalse('temp' in self.body)

    def test_iteration(self):
        """Iteration"""
        keys = list(self.body)
        self.assertIn('name', keys)
        self.assertIn('age', keys)

    def test_len(self):
        """Length"""
        self.assertEqual(len(self.body), 3)

    def test_bool(self):
        """Boolean"""
        self.assertTrue(bool(self.body))
        self.assertFalse(bool(DynamicBody({})))

    def test_to_dict(self):
        """Convert to dict"""
        data = self.body.to_dict()
        self.assertEqual(data['name'], 'test')

    def test_equality(self):
        """Equality"""
        other = DynamicBody({'name': 'test', 'age': 18, 'user': {'id': 1, 'role': 'admin'}})
        self.assertEqual(self.body, other)
        self.assertEqual(self.body, {'name': 'test', 'age': 18, 'user': {'id': 1, 'role': 'admin'}})

    def test_update(self):
        """Update data"""
        self.body.update({'email': 'test@example.com'})
        self.assertEqual(self.body.email, 'test@example.com')

    def test_copy(self):
        """Shallow copy"""
        copy = self.body.copy()
        self.assertEqual(copy.name, 'test')
        copy.name = 'modified'
        self.assertEqual(self.body.name, 'test')  # original unchanged

