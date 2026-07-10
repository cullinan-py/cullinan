# -*- coding: utf-8 -*-
"""Parameter syntax unification tests"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_required_classmethod():
    """Test .as_required() class method"""
    print("1. Testing .as_required() class method...")

    from cullinan.web.params import Query, Body, Header, File, Path

    # Query.as_required()
    q = Query.as_required(int)
    assert q.required == True, f"Query.as_required() should set required=True, got {q.required}"
    assert q.type_ == int, f"Query.as_required(int) should have type_=int, got {q.type_}"

    # Body.as_required()
    b = Body.as_required(str, min_length=1)
    assert b.required == True
    assert b.type_ == str
    assert b.min_length == 1

    # Header.as_required()
    h = Header.as_required(str, alias="Authorization")
    assert h.required == True
    assert h.alias == "Authorization"

    # File.as_required()
    f = File.as_required(max_size=5*1024*1024)
    assert f.required == True
    assert f.max_size == 5*1024*1024

    # Path is required by default, no need for as_required()
    p = Path(int)
    assert p.required == True

    print("   .as_required() class method test passed")


def test_default_value_syntax():
    """Test default value syntax param: Type = ParamType(...)"""
    print("2. Testing default value syntax...")

    from cullinan.web.params import Query, Body, Header, File, ParamResolver

    def handler(
        self,
        # New unified syntax
        page: int = Query(default=1),
        name: str = Body(required=True),
        auth: str = Header(alias="Authorization"),
        avatar: File = File(max_size=5*1024*1024),
    ):
        pass

    config = ParamResolver.analyze_params(handler)

    assert config['page']['source'] == 'query', f"page source: {config['page']['source']}"
    assert config['page']['type'] == int
    assert config['page']['default'] == 1

    assert config['name']['source'] == 'body', f"name source: {config['name']['source']}"
    assert config['name']['required'] == True

    assert config['auth']['source'] == 'header', f"auth source: {config['auth']['source']}"
    assert config['auth']['param_spec'].alias == "Authorization"

    assert config['avatar']['source'] == 'file', f"avatar source: {config['avatar']['source']}"

    print("   Default value syntax test passed")


def test_pure_type_annotation_as_query():
    """Test pure type annotation defaults to Query"""
    print("3. Testing pure type annotation as Query...")

    from cullinan.web.params import ParamResolver

    def handler(
        self,
        page: int,           # Should be Query(int)
        size: int = 10,      # Should be Query(int, default=10)
        name: str = "test",  # Should be Query(str, default="test")
        flag: bool = False,  # Should be Query(bool, default=False)
    ):
        pass

    config = ParamResolver.analyze_params(handler)

    assert config['page']['source'] == 'query', f"page source: {config['page']['source']}"
    assert config['page']['type'] == int
    assert config['page']['required'] == True

    assert config['size']['source'] == 'query', f"size source: {config['size']['source']}"
    assert config['size']['default'] == 10
    assert config['size']['required'] == False

    assert config['name']['source'] == 'query', f"name source: {config['name']['source']}"
    assert config['name']['default'] == "test"

    assert config['flag']['source'] == 'query', f"flag source: {config['flag']['source']}"
    assert config['flag']['default'] == False

    print("   Pure type annotation default Query test passed")


def test_file_required_syntax():
    """Test File.as_required() syntax"""
    print("4. Testing File.as_required() syntax...")

    from cullinan.web.params import File, ParamResolver

    def handler(
        self,
        avatar: File = File.as_required(max_size=5*1024*1024, allowed_types=['image/*']),
    ):
        pass

    config = ParamResolver.analyze_params(handler)

    assert config['avatar']['source'] == 'file'
    assert config['avatar']['required'] == True
    assert config['avatar']['param_spec'].max_size == 5*1024*1024
    assert config['avatar']['param_spec'].allowed_types == ['image/*']

    print("   File.as_required() syntax test passed")


def test_backward_compatibility():
    """Test backward compatibility"""
    print("5. Testing backward compatibility...")

    from cullinan.web.params import Path, Query, Body, Header, DynamicBody, RawBody, ParamResolver

    # Old syntax still valid
    def old_style(
        self,
        id: Path(int),
        page: Query(int, default=1),
        name: Body(str, required=True),
        auth: Header(str, alias="Authorization"),
        body: DynamicBody,
        raw: RawBody,
    ):
        pass

    config = ParamResolver.analyze_params(old_style)

    assert config['id']['source'] == 'path'
    assert config['page']['source'] == 'query'
    assert config['name']['source'] == 'body'
    assert config['auth']['source'] == 'header'
    assert config['body']['source'] == 'body'
    assert config['raw']['source'] == 'raw_body'

    print("   Backward compatibility test passed")


def test_mixed_syntax():
    """Test mixed syntax"""
    print("6. Testing mixed syntax...")

    from cullinan.web.params import Path, Query, Body, Header, File, DynamicBody, ParamResolver

    def handler(
        self,
        # Old syntax
        id: Path(int),
        # New syntax (default value style)
        page: int = Query(default=1),
        name: str = Body(required=True),
        # Pure type annotation (as Query)
        limit: int = 100,
        # File.as_required()
        avatar: File = File.as_required(max_size=5*1024*1024),
        # DynamicBody
        extra: DynamicBody = None,
    ):
        pass

    config = ParamResolver.analyze_params(handler)

    assert config['id']['source'] == 'path'
    assert config['page']['source'] == 'query'
    assert config['name']['source'] == 'body'
    assert config['limit']['source'] == 'query'
    assert config['limit']['default'] == 100
    assert config['avatar']['source'] == 'file'
    assert config['avatar']['required'] == True
    assert config['extra']['source'] == 'body'

    print("   Mixed syntax test passed")
