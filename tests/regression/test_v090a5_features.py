# -*- coding: utf-8 -*-
"""v0.90a5 new features tests"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_imports():
    """Test all new module imports"""
    print("1. Testing imports...")
    
    from cullinan.web.params import (
        FileInfo, FileList,
        field_validator, FieldValidationError, validated_dataclass,
        Response, ResponseModel, ResponseSerializer, serialize_response,
    )
    
    print("   All modules imported successfully")


def test_file_info():
    """Test FileInfo"""
    print("2. Testing FileInfo...")
    
    from cullinan.web.params import FileInfo, FileList
    
    # Create FileInfo
    file = FileInfo(
        filename='test.png',
        body=b'fake image data',
        content_type='image/png',
    )
    
    assert file.filename == 'test.png'
    assert file.size == 15
    assert file.content_type == 'image/png'
    assert file.extension == 'png'
    assert file.is_image() == True
    assert file.is_pdf() == False
    assert file.match_type('image/*') == True
    assert file.match_type('application/pdf') == False
    
    # FileList
    files = FileList([
        FileInfo('a.png', b'data1', 'image/png'),
        FileInfo('b.jpg', b'data2', 'image/jpeg'),
        FileInfo('c.pdf', b'data3', 'application/pdf'),
    ])
    
    assert len(files) == 3
    assert files.count == 3
    assert 'a.png' in files.filenames
    
    images = files.filter_by_type('image/*')
    assert len(images) == 2
    
    print("   FileInfo test passed")


def test_field_validator():
    """Test field_validator"""
    print("3. Testing field_validator...")
    
    from dataclasses import dataclass
    from cullinan.web.params import field_validator, validated_dataclass, FieldValidationError
    
    @validated_dataclass
    class User:
        name: str
        email: str
        age: int = 0
        
        @field_validator('email')
        @classmethod
        def validate_email(cls, v):
            if '@' not in str(v):
                raise ValueError('Invalid email')
            return v
        
        @field_validator('age')
        @classmethod
        def validate_age(cls, v):
            if v < 0:
                raise ValueError('Age must be positive')
            return v
    
    # Normal case
    user = User(name='John', email='john@example.com', age=25)
    assert user.name == 'John'
    assert user.email == 'john@example.com'
    
    # Validation failure
    try:
        user = User(name='John', email='invalid', age=25)
        assert False, "Should have raised error"
    except FieldValidationError as e:
        assert e.field == 'email'
    
    print("   field_validator test passed")


def test_response():
    """Test Response decorator"""
    print("4. Testing Response...")
    
    from dataclasses import dataclass
    from cullinan.web.params import Response, get_response_models, ResponseSerializer
    
    @dataclass
    class UserResponse:
        id: int
        name: str
    
    @Response(model=UserResponse, status_code=200, description="Success")
    @Response(status_code=404, description="Not found")
    def get_user(user_id):
        pass
    
    models = get_response_models(get_user)
    assert len(models) == 2, f"Expected 2 models, got {len(models)}"
    # Note: decorator stacking order is bottom-up, so 404 is added first, 200 is added later
    status_codes = [m.status_code for m in models]
    assert 200 in status_codes, f"200 not in {status_codes}"
    assert 404 in status_codes, f"404 not in {status_codes}"

    # Test serialization
    user = UserResponse(id=1, name='John')
    result = ResponseSerializer.serialize(user)
    assert result == {'id': 1, 'name': 'John'}, f"Got {result}"

    # Test JSON
    json_str = ResponseSerializer.to_json(user)
    assert '"id": 1' in json_str or '"id":1' in json_str, f"Got {json_str}"

    print("   Response test passed")


def test_file_param_enhanced():
    """Test enhanced File parameters"""
    print("5. Testing enhanced File parameters...")
    
    from cullinan.web.params import File, FileInfo
    
    # Create a File parameter with validation
    file_param = File(
        max_size=1024,
        min_size=10,
        allowed_types=['image/*', 'application/pdf'],
        multiple=False,
    )
    
    assert file_param.max_size == 1024
    assert file_param.min_size == 10
    assert file_param.multiple == False
    
    # Validation passes
    valid_file = FileInfo('test.png', b'x' * 100, 'image/png')
    file_param.validate_file(valid_file)  # No exception
    
    # File too large
    large_file = FileInfo('test.png', b'x' * 2000, 'image/png')
    try:
        file_param.validate_file(large_file)
        assert False, "Should have raised error"
    except ValueError as e:
        assert 'exceeds maximum' in str(e)
    
    # Type not allowed
    wrong_type = FileInfo('test.txt', b'x' * 100, 'text/plain')
    try:
        file_param.validate_file(wrong_type)
        assert False, "Should have raised error"
    except ValueError as e:
        assert 'not allowed' in str(e)
    
    print("   File parameter enhancement test passed")


def test_response_serializer():
    """Test ResponseSerializer"""
    print("6. Testing ResponseSerializer...")
    
    from dataclasses import dataclass
    from typing import List
    from cullinan.web.params import ResponseSerializer, DynamicBody
    
    @dataclass
    class Address:
        city: str
        zip_code: str
    
    @dataclass
    class User:
        id: int
        name: str
        address: Address
        tags: List[str]
    
    user = User(
        id=1,
        name='John',
        address=Address(city='NYC', zip_code='10001'),
        tags=['admin', 'active'],
    )
    
    result = ResponseSerializer.serialize(user)
    
    assert result['id'] == 1
    assert result['name'] == 'John'
    assert result['address']['city'] == 'NYC'
    assert result['tags'] == ['admin', 'active']
    
    # Test DynamicBody
    body = DynamicBody({'name': 'Test', 'value': 123})
    result = ResponseSerializer.serialize(body)
    assert result == {'name': 'Test', 'value': 123}
    
    print("   ResponseSerializer test passed")


def test_file_resolver():
    """Test file parameter resolver"""
    print("7. Testing file parameter resolver...")

    from cullinan.web.params import File, FileInfo, FileList
    from cullinan.web.params.resolver import ParamResolver

    # Simulate Tornado file format
    tornado_file = {
        'filename': 'test.png',
        'body': b'fake image content',
        'content_type': 'image/png',
    }

    # Test single file resolution
    file_spec = File(max_size=1024 * 1024)
    result = ParamResolver._resolve_file_param([tornado_file], file_spec, 'avatar')

    assert isinstance(result, FileInfo)
    assert result.filename == 'test.png'
    assert result.size == 18
    assert result.content_type == 'image/png'

    # Test multi-file resolution
    file_spec_multi = File(multiple=True, max_count=10)
    files_data = [
        {'filename': 'a.png', 'body': b'data1', 'content_type': 'image/png'},
        {'filename': 'b.jpg', 'body': b'data2', 'content_type': 'image/jpeg'},
    ]

    result = ParamResolver._resolve_file_param(files_data, file_spec_multi, 'files')

    assert isinstance(result, FileList)
    assert len(result) == 2
    assert result[0].filename == 'a.png'
    assert result[1].filename == 'b.jpg'

    print("   File parameter resolver test passed")
