# -*- coding: utf-8 -*-
"""DynamicBody Enhanced Feature Tests

Tests newly added empty-check and safe-access methods.

Author: Cullinan
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cullinan.web.params import DynamicBody, SafeAccessor, EMPTY


def test_basic_access():
    """Test basic access"""
    print("1. Testing basic access...")
    body = DynamicBody({'name': 'John', 'age': 25})
    
    assert body.name == 'John'
    assert body.age == 25
    assert body.get('name') == 'John'
    assert body.get('missing', 'default') == 'default'
    
    print("   PASSED")


def test_has_method():
    """Test has method"""
    print("2. Testing has method...")
    body = DynamicBody({'name': 'John', 'email': None, 'empty_str': ''})
    
    assert body.has('name') == True
    assert body.has('email') == True  # exists but value is None
    assert body.has('missing') == False
    assert body.has('empty_str') == True
    
    print("   PASSED")


def test_has_value_method():
    """Test has_value method"""
    print("3. Testing has_value method...")
    body = DynamicBody({
        'name': 'John',
        'email': None,
        'empty_str': '',
        'empty_list': [],
        'zero': 0,
        'valid_list': [1, 2, 3],
    })
    
    assert body.has_value('name') == True
    assert body.has_value('email') == False  # None
    assert body.has_value('empty_str') == False  # ''
    assert body.has_value('empty_list') == False  # []
    assert body.has_value('zero') == False  # 0 is falsy
    assert body.has_value('valid_list') == True
    assert body.has_value('missing') == False
    
    print("   PASSED")


def test_is_empty_methods():
    """Test is_empty and is_not_empty methods"""
    print("4. Testing is_empty/is_not_empty methods...")
    
    empty_body = DynamicBody({})
    assert empty_body.is_empty() == True
    assert empty_body.is_not_empty() == False
    
    body = DynamicBody({'name': 'John'})
    assert body.is_empty() == False
    assert body.is_not_empty() == True
    
    print("   PASSED")


def test_is_null_methods():
    """Test is_null and is_not_null methods"""
    print("5. Testing is_null/is_not_null methods...")
    body = DynamicBody({'name': 'John', 'email': None})
    
    assert body.is_null('name') == False
    assert body.is_not_null('name') == True
    
    assert body.is_null('email') == True  # None
    assert body.is_not_null('email') == False
    
    assert body.is_null('missing') == True  # does not exist
    assert body.is_not_null('missing') == False
    
    print("   PASSED")


def test_get_nested():
    """Test nested safe access"""
    print("6. Testing get_nested method...")
    body = DynamicBody({
        'user': {
            'name': 'John',
            'address': {
                'city': 'New York',
                'zip': '10001'
            }
        }
    })
    
    # Existing nested path
    assert body.get_nested('user.name') == 'John'
    assert body.get_nested('user.address.city') == 'New York'
    
    # Non-existent nested path
    assert body.get_nested('user.phone', 'N/A') == 'N/A'
    assert body.get_nested('user.address.country', 'USA') == 'USA'
    assert body.get_nested('missing.path.deep', 'default') == 'default'
    
    # Nested returns DynamicBody
    address = body.get_nested('user.address')
    assert isinstance(address, DynamicBody)
    assert address.city == 'New York'
    
    print("   PASSED")


def test_typed_getters():
    """Test typed getter methods"""
    print("7. Testing typed getter methods...")
    body = DynamicBody({
        'name': 'John',
        'age': 25,
        'price': 19.99,
        'active': True,
        'active_str': 'true',
        'tags': ['a', 'b', 'c'],
        'invalid_int': 'not_a_number',
    })
    
    # get_str
    assert body.get_str('name') == 'John'
    assert body.get_str('age') == '25'  # converted to string
    assert body.get_str('missing') == ''
    assert body.get_str('missing', 'default') == 'default'
    
    # get_int
    assert body.get_int('age') == 25
    assert body.get_int('missing') == 0
    assert body.get_int('missing', 100) == 100
    assert body.get_int('invalid_int') == 0  # conversion failure returns default
    
    # get_float
    assert body.get_float('price') == 19.99
    assert body.get_float('age') == 25.0
    assert body.get_float('missing') == 0.0
    
    # get_bool
    assert body.get_bool('active') == True
    assert body.get_bool('active_str') == True
    assert body.get_bool('missing') == False
    
    # get_list
    assert body.get_list('tags') == ['a', 'b', 'c']
    assert body.get_list('missing') == []
    assert body.get_list('missing', ['default']) == ['default']
    assert body.get_list('name') == []  # non-list returns default
    
    print("   PASSED")


def test_safe_accessor_basic():
    """Test SafeAccessor basic functionality"""
    print("8. Testing SafeAccessor basic functionality...")
    body = DynamicBody({
        'user': {
            'name': 'John',
            'address': {
                'city': 'New York'
            }
        }
    })
    
    # Access existing attributes
    assert body.safe.user.name.value == 'John'
    assert body.safe.user.address.city.value == 'New York'
    
    # Access non-existent attributes
    assert body.safe.user.phone.value is None
    assert body.safe.user.phone.value_or('N/A') == 'N/A'
    assert body.safe.missing.deep.path.value_or('default') == 'default'
    
    print("   PASSED")


def test_safe_accessor_exists():
    """Test SafeAccessor existence check"""
    print("9. Testing SafeAccessor exists/is_null/is_not_null...")
    body = DynamicBody({
        'user': {'name': 'John', 'email': None}
    })
    
    # exists
    assert body.safe.user.exists == True
    assert body.safe.user.name.exists == True
    assert body.safe.user.phone.exists == False
    assert body.safe.missing.exists == False
    
    # is_null / is_not_null
    assert body.safe.user.name.is_null == False
    assert body.safe.user.name.is_not_null == True
    assert body.safe.user.email.is_null == True  # None
    assert body.safe.user.phone.is_null == True  # does not exist
    
    print("   PASSED")


def test_safe_accessor_bool():
    """Test SafeAccessor boolean conversion"""
    print("10. Testing SafeAccessor boolean conversion...")
    body = DynamicBody({
        'active': True,
        'inactive': False,
        'name': 'John',
        'empty': '',
    })
    
    assert bool(body.safe.active) == True
    assert bool(body.safe.inactive) == False
    assert bool(body.safe.name) == True
    assert bool(body.safe.empty) == False
    assert bool(body.safe.missing) == False
    
    print("   PASSED")


def test_backward_compatibility():
    """Test backward compatibility"""
    print("11. Testing backward compatibility...")
    body = DynamicBody({'name': 'John', 'age': 25})
    
    # Original functionality still works
    assert body.name == 'John'
    assert body['name'] == 'John'
    assert 'name' in body
    assert body.get('name') == 'John'
    assert body.to_dict() == {'name': 'John', 'age': 25}
    assert len(body) == 2
    assert bool(body) == True
    
    # Iteration
    keys = list(body.keys())
    assert 'name' in keys
    assert 'age' in keys
    
    print("   PASSED")


def test_empty_sentinel():
    """Test EMPTY sentinel"""
    print("12. Testing EMPTY sentinel...")
    
    assert bool(EMPTY) == False
    assert EMPTY is EMPTY  # singleton
    
    # EMPTY is not None
    assert EMPTY is not None
    
    print("   PASSED")


def test_complex_nested():
    """Test complex nested scenarios"""
    print("13. Testing complex nested scenarios...")
    body = DynamicBody({
        'users': [
            {'name': 'John', 'role': 'admin'},
            {'name': 'Jane', 'role': 'user'}
        ],
        'config': {
            'debug': True,
            'database': {
                'host': 'localhost',
                'port': 5432
            }
        }
    })
    
    # Access via get_nested
    assert body.get_nested('config.debug') == True
    assert body.get_nested('config.database.host') == 'localhost'
    assert body.get_nested('config.database.port') == 5432
    
    # List needs direct access
    assert len(body.users) == 2
    
    # safe accessor
    assert body.safe.config.database.host.value == 'localhost'
    assert body.safe.config.missing.deep.value_or('default') == 'default'
    
    print("   PASSED")

